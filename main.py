import gradio as gr
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Tag
from openai import OpenAI
import re
import os
import tempfile
from langdetect import detect, DetectorFactory
from typing import List, Tuple, Optional, Dict, Any
import magic # python-magic
import traceback # Para logging de erros detalhado
import locale
from translations import translations

# Para garantir resultados consistentes da langdetect
DetectorFactory.seed = 0

# --- Constantes e Configurações ---
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_OLLAMA_API_KEY = "ollama" # Necessário pela API, mas não usado pelo Ollama
SUGGESTED_MODELS = ["qwen3:14b", "mistral", "phi4"]
DEFAULT_MODEL = SUGGESTED_MODELS[0] if SUGGESTED_MODELS else "qwen3:14b"
MAX_EPUB_SIZE_MB = 50
COMMON_LANGUAGES = [
    ("Auto-Detect", "auto"),
    ("English", "EN"),
    ("Portuguese (Brazil)", "PT-BR"),
    ("Portuguese (Portugal)", "PT-PT"),
    ("Spanish", "ES"),
    ("French", "FR"),
    ("German", "DE"),
    ("Italian", "IT"),
    ("Russian", "RU"),
    ("Japanese", "JA"),
    ("Chinese (Simplified)", "ZH-CN"),
    ("Polish", "PL"),
]

# --- Lógica Principal de Tradução (Sem alterações) ---

# 👇 ADICIONADO: Função para determinar o idioma inicial
def get_initial_lang():
    """Detecta o idioma do sistema ou usa 'en' como padrão."""
    try:
        system_lang = locale.getlocale()[0] or "en_US"
        if system_lang:
            lang_code = system_lang.split('_')[0]
            if lang_code in translations:
                return lang_code
    except Exception:
        pass
    return 'en'
initial_lang = get_initial_lang()

def system_prompt(from_lang: str, to_lang: str) -> str:
    return (
        f"You are an expert {from_lang}-to-{to_lang} translator. "
        f"Translate the given HTML content. Keep all original HTML tags and structure intact. "
        f"Ensure that only the text content within the tags is translated. "
        f"Return only the translated HTML content for the given fragment. /no_think"
    )

def translate_chunk(client: OpenAI, html_fragment: str, model_name: str, from_lang: str, to_lang: str) -> str:
    """Traduz um fragmento HTML."""
    if not html_fragment.strip():
        return html_fragment
    try:
        print(f"TRANSLATE_CHUNK: Enviando para o modelo {model_name}. De: {from_lang}, Para: {to_lang}. Tamanho do fragmento: {len(html_fragment)} chars.")
        print(f"TRANSLATE_CHUNK: Conteúdo do fragmento (primeiros 300 chars):\n{html_fragment[:300]}")
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.2,
            messages=[
                {'role': 'system', 'content': system_prompt(from_lang, to_lang)},
                {'role': 'user', 'content': html_fragment},
            ],
            timeout=180
        )
        translated_text = response.choices[0].message.content
        translated_text = re.sub(r'<think>.*?</think>', '', translated_text, flags=re.DOTALL).strip()
        print(f"TRANSLATE_CHUNK: Recebido do modelo {model_name}. Tamanho da tradução: {len(translated_text)} chars.")
        print(f"TRANSLATE_CHUNK: Conteúdo traduzido (primeiros 300 chars):\n{translated_text[:300]}")
        translated_text = translated_text.replace('<think>', '').replace('</think>', '')
        print(f"TRANSLATE_CHUNK: Fragmento traduzido final (após limpeza):\n{translated_text}")
        return translated_text
    except Exception as e:
        print(f"TRANSLATE_CHUNK: ERRO ao traduzir fragmento com modelo {model_name}. Erro: {e}")
        traceback.print_exc()
        gr.Warning(f"Error translating an HTML fragment with model {model_name}: {type(e).__name__}. Original fragment will be used.")
        return html_fragment

def translate_html_block_elements(
    client: OpenAI,
    soup: BeautifulSoup,
    model_name: str,
    from_lang: str,
    to_lang: str,
    chapter_name: str,
    progress_callback_chapter_blocks=None
):
    """Itera sobre elementos de bloco no BeautifulSoup object, traduz seu conteúdo HTML e substitui o elemento original pelo traduzido."""
    block_selectors = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'div', 'caption', 'td', 'th', 'dt', 'dd']
    elements_to_translate = []
    for selector in block_selectors:
        elements_to_translate.extend(soup.find_all(selector))

    if not elements_to_translate:
        all_text_nodes_in_body = soup.body.find_all(string=True, recursive=False) if soup.body else []
        temp_elements = []
        for text_node in all_text_nodes_in_body:
            if text_node.strip():
                wrapper_span = soup.new_tag("span", attrs={"data-text-node": "true"})
                text_node.wrap(wrapper_span)
                temp_elements.append(wrapper_span)
        if temp_elements:
            gr.Info(f"No common block elements found in '{chapter_name}'. Processing loose text nodes directly within <body>.")
            print(f"TRANSLATE_HTML_BLOCKS: Nenhum elemento de bloco comum encontrado em '{chapter_name}'. Processando nós de texto soltos.")
            elements_to_translate = temp_elements
        else:
            gr.Warning(f"No translatable block elements or direct text content found in chapter '{chapter_name}'. Skipping.")
            print(f"TRANSLATE_HTML_BLOCKS: Nenhum bloco traduzível ou conteúdo de texto direto encontrado no capítulo '{chapter_name}'. Pulando.")
            return

    num_blocks = len(elements_to_translate)
    if num_blocks == 0:
        print(f"TRANSLATE_HTML_BLOCKS: Capítulo '{chapter_name}': Encontrados {num_blocks} blocos/elementos HTML para traduzir.")
        gr.Info(f"Chapter '{chapter_name}' has no content blocks to translate.")
        return

    print(f"Chapter '{chapter_name}': Found {num_blocks} HTML blocks/elements to translate.")

    for i, element_tag in enumerate(elements_to_translate):
        if progress_callback_chapter_blocks:
            progress_callback_chapter_blocks( (i + 1) / num_blocks )

        if not element_tag.parent:
            print(f"TRANSLATE_HTML_BLOCKS: Pulando elemento {element_tag.name} (bloco {i+1}/{num_blocks}) pois não está mais na árvore (provavelmente parte de um pai já traduzido).")
            continue

        original_html_fragment = str(element_tag)
        if not original_html_fragment.strip():
            continue

        print(f"TRANSLATE_HTML_BLOCKS: Traduzindo bloco {i+1}/{num_blocks} do capítulo '{chapter_name}' (tag: {element_tag.name}, ID do elemento na lista: {i}). Tamanho original: {len(original_html_fragment)} chars.")
        translated_html_str = translate_chunk(client, original_html_fragment, model_name, from_lang, to_lang)

        if translated_html_str and translated_html_str.strip() != original_html_fragment.strip():
            print(f"TRANSLATE_HTML_BLOCKS: Bloco {i+1}/{num_blocks} ('{element_tag.name}') traduzido. Tentando substituir no DOM. Tamanho traduzido: {len(translated_html_str)} chars.")
            try:
                translated_soup_fragment = BeautifulSoup(translated_html_str, 'html.parser')
                new_element = None
                if translated_soup_fragment.body and translated_soup_fragment.body.contents:
                    if len(translated_soup_fragment.body.contents) == 1 and isinstance(translated_soup_fragment.body.contents[0], Tag):
                        new_element = translated_soup_fragment.body.contents[0]
                    else:
                        new_element = translated_soup_fragment.body.find(lambda tag: isinstance(tag, Tag), recursive=False)
                        if not new_element:
                            temp_span = soup.new_tag("span", attrs={"data-translated-wrapper": "true"})
                            for content_item in translated_soup_fragment.body.contents:
                                temp_span.append(content_item.extract())
                            new_element = temp_span
                elif translated_soup_fragment.contents and isinstance(translated_soup_fragment.contents[0], Tag):
                    new_element = translated_soup_fragment.contents[0]

                if new_element:
                    element_tag.replace_with(new_element)
                else:
                    if element_tag.name == "span" and element_tag.get("data-text-node") == "true":
                        element_tag.string = translated_soup_fragment.get_text()
                    else:
                        gr.Warning(f"Translated content for a block in '{chapter_name}' was not a single valid HTML element. Inserting as text if possible or keeping original.")
                        print(f"TRANSLATE_HTML_BLOCKS: Conteúdo traduzido para o bloco {i+1}/{num_blocks} em '{chapter_name}' não era um elemento HTML único válido.")
                        element_tag.string = translated_soup_fragment.get_text()
            except Exception as e:
                print(f"TRANSLATE_HTML_BLOCKS: ERRO ao parsear ou substituir bloco HTML traduzido no capítulo '{chapter_name}'. Bloco {i+1}/{num_blocks} (tag: {element_tag.name}). Erro: {e}")
                traceback.print_exc()
                gr.Warning(f"Could not process translated block in '{chapter_name}': {type(e).__name__}. Original content kept for this block.")


# --- Funções Auxiliares Gradio (Com Alterações) ---

def get_epub_chapters_details(epub_path: str) -> List[Dict[str, Any]]:
    print(f"GET_EPUB_CHAPTERS_DETAILS: Iniciando extração de detalhes dos capítulos para: {epub_path}")
    try:
        book = epub.read_epub(epub_path)
        chapters = []
        for i, item in enumerate(book.get_items_of_type(ebooklib.ITEM_DOCUMENT)):
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text_content = soup.get_text()
            title_tag = soup.find(['h1', 'h2'])
            chapter_display_name = title_tag.get_text(strip=True) if title_tag else item.get_name()
            if not chapter_display_name:  chapter_display_name = f"Chapter Document {i+1}"
            chapters.append({
                "id": item.get_name(),
                "name": chapter_display_name,
                "char_count": len(text_content),
                "preview": text_content[:200].strip().replace('\n', ' ')
            })
        print(f"GET_EPUB_CHAPTERS_DETAILS: Detalhes de {len(chapters)} capítulos extraídos com sucesso para: {epub_path}")
        return chapters
    except Exception as e:
        print(f"GET_EPUB_CHAPTERS_DETAILS: ERRO ao ler EPUB para detalhes dos capítulos. Caminho: {epub_path}. Erro: {e}")
        traceback.print_exc()
        return []

def parse_epub_metadata_and_chapters(epub_file_obj: Optional[tempfile._TemporaryFileWrapper]):
    """
    Processa o EPUB, extrai metadados e detalhes dos capítulos, e retorna tanto as atualizações da UI
    quanto um dicionário de estado com os dados completos do livro.
    """
    if epub_file_obj is None:
        print("PARSE_EPUB_METADATA: Upload limpo. Resetando campos da UI.")
        return (
            gr.update(choices=[], value=[], label=t['chapters_selector_label'], interactive=False),
            gr.update(value="auto"),
            gr.update(value="PT-BR"),
            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=""),
            {}  # Limpa o estado do livro
        )

    epub_path = epub_file_obj.name
    file_size_mb = os.path.getsize(epub_path) / (1024 * 1024)
    print(f"PARSE_EPUB_METADATA: Processando arquivo: {epub_path}, Tamanho: {file_size_mb:.2f} MB")

    try:
        file_type = magic.from_file(epub_path, mime=True)
        if file_type != 'application/epub+zip':
            gr.Warning(f"Uploaded file MIME type ({file_type}) is not 'application/epub+zip'. Processing will continue but may fail.")
    except Exception as e:
        gr.Warning(f"Could not verify file MIME type: {e}.")

    if file_size_mb > MAX_EPUB_SIZE_MB:
        gr.Error(f"EPUB file size ({file_size_mb:.2f} MB) exceeds the limit of {MAX_EPUB_SIZE_MB} MB.")
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), {}

    try:
        book = epub.read_epub(epub_path)
    except Exception as e:
        gr.Error(f"Error reading EPUB file: {e}. It might be corrupted or not a valid EPUB.")
        traceback.print_exc()
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), {}

    title_meta = book.get_metadata('DC', 'title')
    title_str = title_meta[0][0] if title_meta else "Unknown Title"
    authors_meta = book.get_metadata('DC', 'creator')
    author_str = ', '.join([a[0] for a in authors_meta]) if authors_meta else "Unknown Author"

    chapters_details = get_epub_chapters_details(epub_path)
    num_chapters = len(chapters_details)
    chapter_choices_for_ui = [(f"Ch. {i+1}: {ch['name']} ({ch['char_count']} chars) - \"{ch['preview']}...\"", i) for i, ch in enumerate(chapters_details)]

    detected_lang_code = "auto"
    try:
        sample_text = " ".join([ch['preview'] for ch in chapters_details[:5]])
        if sample_text.strip():
            detected_lang = detect(sample_text.strip()).split('-')[0].upper()
            match = next((code for name, code in COMMON_LANGUAGES if code != "auto" and detected_lang.startswith(code)), None)
            if match:
                detected_lang_code = match
                gr.Info(f"Detected source language: {detected_lang_code}")
            else:
                gr.Info(f"Detected language '{detected_lang}' not in predefined list. Defaulting to 'Auto-Detect'.")
    except Exception as e:
        gr.Warning(f"Language detection failed: {type(e).__name__}. Defaulting to 'Auto-Detect'.")

    from_lang_value = detected_lang_code if detected_lang_code != "auto" else "auto"

    # Cria o dicionário de estado com todos os dados do livro
    book_data = {
        "title": title_str,
        "author": author_str,
        "chapter_details": chapters_details,
        "chapter_choices_for_ui": chapter_choices_for_ui,
        "detected_lang": from_lang_value
    }

    # Retorna as atualizações da UI e o dicionário de estado
    return (
        gr.update(choices=chapter_choices_for_ui, value=list(range(num_chapters)), label=f"Chapters to Translate ({num_chapters} found)", interactive=True),
        gr.update(value=from_lang_value),
        gr.update(), # lang_to_dropdown
        gr.update(value=title_str),
        gr.update(value=author_str),
        gr.update(value=f"{num_chapters} chapter documents found in the EPUB."),
        book_data # Popula o book_data_state
    )

def gradio_translate_epub(
    epub_file_obj: tempfile._TemporaryFileWrapper,
    model_name: str,
    from_lang_ui: str,
    to_lang_ui: str,
    selected_chapter_indices: List[int],
    progress=gr.Progress(track_tqdm=True)
):
    if not epub_file_obj:
        gr.Error("Please upload an EPUB file first.")
        return None
    if not model_name:
        gr.Error("Please enter or select an Ollama model name.")
        return None
    if not selected_chapter_indices:
        gr.Warning("No chapters selected for translation. Nothing to do.")
        return None

    input_epub_path = epub_file_obj.name

    final_from_lang = from_lang_ui
    if final_from_lang == "auto":
        try:
            temp_book_for_lang_detect = epub.read_epub(input_epub_path)
            sample_text = ""
            for item_idx, item_doc in enumerate(temp_book_for_lang_detect.get_items_of_type(ebooklib.ITEM_DOCUMENT)):
                if item_idx < 5:
                    soup = BeautifulSoup(item_doc.get_content(), 'html.parser')
                    sample_text += soup.get_text(separator=' ', strip=True)[:200] + " "
                if len(sample_text) > 1000: break

            if sample_text.strip():
                detected = detect(sample_text.strip()).upper().split('-')[0]
                if any(detected == lang_tuple[1] for lang_tuple in COMMON_LANGUAGES if lang_tuple[1] != "auto"):
                    final_from_lang = detected
                    gr.Info(f"Auto-detected source language for translation as: {final_from_lang}")
                else:
                    final_from_lang = "EN"
                    gr.Info(f"Could not robustly auto-detect source language. Assuming '{final_from_lang}'.")
            else:
                final_from_lang = "EN"
                gr.Info(f"Not enough text to auto-detect source language. Assuming '{final_from_lang}'.")
        except Exception as e:
            final_from_lang = "EN"
            gr.Warning(f"Error during pre-translation language auto-detection: {type(e).__name__}. Assuming '{final_from_lang}'.")

    try:
        client = OpenAI(base_url=DEFAULT_OLLAMA_BASE_URL, api_key=DEFAULT_OLLAMA_API_KEY)
        try:
            client.models.list()
        except Exception as conn_err:
            gr.Error(f"Failed to connect to Ollama server at {DEFAULT_OLLAMA_BASE_URL}. Error: {type(conn_err).__name__} - {conn_err}")
            return None

        book = epub.read_epub(input_epub_path)
        all_document_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        chapters_to_process_items = [all_document_items[i] for i in selected_chapter_indices if 0 <= i < len(all_document_items)]

        if not chapters_to_process_items:
            gr.Error("No valid chapters selected or found for processing.")
            return None

        total_chapters_for_progress = len(chapters_to_process_items)
        progress(0, desc="Starting translation...")

        for i, item_to_translate in enumerate(chapters_to_process_items):
            item_id_or_name = item_to_translate.get_name() or f"Document Index {all_document_items.index(item_to_translate)}"
            progress_desc = f"Translating Ch. {i+1}/{total_chapters_for_progress} ('{item_id_or_name}')..."
            progress( i / total_chapters_for_progress, desc=progress_desc)
            print(f"Processing chapter {i+1}/{total_chapters_for_progress}: {item_id_or_name}")

            try:
                soup = BeautifulSoup(item_to_translate.get_content(), 'html.parser')
                translate_html_block_elements(client, soup, model_name, final_from_lang, to_lang_ui, item_id_or_name)
                item_to_translate.set_content(str(soup).encode('utf-8'))
            except Exception as e_chap:
                gr.Warning(f"Failed to process chapter '{item_id_or_name}': {type(e_chap).__name__}. It may be left untranslated.")
                traceback.print_exc()

        progress(1, desc="Translation complete! Finalizing EPUB...")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".epub", prefix="translated_") as tmp_output_file:
            output_epub_path = tmp_output_file.name
        epub.write_epub(output_epub_path, book, {})
        print(f"GRADIO_TRANSLATE_EPUB: EPUB traduzido salvo em: {output_epub_path}")
        gr.Info("EPUB translation successful!")
        return output_epub_path
    except Exception as e_main:
        gr.Error(f"An unexpected error occurred: {type(e_main).__name__} - {e_main}")
        traceback.print_exc()
        return None

# --- Interface Gradio (Com Alterações) ---
css = """
.contain{ max-width: 660px; margin: 0 auto; }
.detalhes .form{ border: none; }
.BookDetails{ padding: 0; }
.meuBloco{ border-radius: 10px; }
.px-0{padding: 0;}
"""

with gr.Blocks(theme='earneleh/paris', css=css) as app:
    t = translations[initial_lang]
    gr.Markdown(t['app_title'])
    gr.Markdown(t['app_subtitle'])

    # NOVO: Estado centralizado para armazenar os dados do livro.
    book_data_state = gr.State({})

    with gr.Row():
        with gr.Column(scale=3, elem_classes=['newBg']):
            gr.Markdown(t['section_1_title'])
            epub_upload_btn = gr.UploadButton(t['upload_button_text'], file_types=[".epub"], type="filepath")

            gr.Markdown(t['section_2_title'])
            model_name_input = gr.Textbox(
                label=t['model_name_label'], 
                placeholder=t['model_name_placeholder'], 
                value=DEFAULT_MODEL, 
                elem_classes="meuBloco"
            )

            with gr.Row(elem_classes="small_gap meuBloco"):
                lang_from_dropdown = gr.Dropdown(
                    label=t['from_language_label'], 
                    choices=COMMON_LANGUAGES, 
                    value="auto", 
                    elem_classes="meuBloco title me-1"
                )
                lang_to_dropdown = gr.Dropdown(
                    label=t['to_language_label'], 
                    choices=[(n, c) for n, c in COMMON_LANGUAGES if c != "auto"], 
                    value="PT-BR", 
                    elem_classes="meuBloco ms-1"
                )

            with gr.Accordion(label=t['chapters_accordion_label'], elem_classes="meuBloco detalhes", open=False):
                with gr.Row():
                    with gr.Column(scale=8, elem_classes=['newBg']):
                        gr.Markdown(t['section_3_title'])
                    with gr.Column(scale=3, elem_classes=['newBg']):
                        # O texto deste botão provavelmente mudará dinamicamente (Select/Deselect All)
                        # mas este é o valor inicial.
                        toggle_chapters_btn = gr.Button(t['deselect_all_btn'])
                chapters_selector = gr.CheckboxGroup(
                    label=t['chapters_selector_label'], 
                    choices=[], 
                    value=[], 
                    interactive=False, 
                    elem_classes="meuBloco px-0"
                )

            with gr.Accordion(label=t['details_accordion_label'], elem_classes="meuBloco detalhes", open=False):
                epub_title_display = gr.Textbox(
                    label=t['book_title_label'], 
                    elem_classes="BookDetails", 
                    interactive=True, 
                    lines=1
                )
                epub_author_display = gr.Textbox(
                    label=t['book_author_label'], 
                    elem_classes="BookDetails", 
                    interactive=True, 
                    lines=1
                )
                chapter_count_display = gr.Textbox(
                    label=t['epub_structure_info_label'], 
                    elem_classes="BookDetails", 
                    interactive=True, 
                    lines=1
                )

            gr.Markdown(t['section_4_title'])
            submit_btn = gr.Button(t['translate_button_text'], variant="primary", scale=2)
            progress_bar = gr.Progress()
            output_file_display = gr.File(label=t['download_label'], interactive=False)

    # --- Eventos Gradio (Com Alterações) ---

    upload_outputs = [
        chapters_selector,
        lang_from_dropdown,
        lang_to_dropdown,
        epub_title_display,
        epub_author_display,
        chapter_count_display,
        book_data_state  # A última saída agora é o estado do livro
    ]

    epub_upload_btn.upload(
        fn=parse_epub_metadata_and_chapters,
        inputs=[epub_upload_btn],
        outputs=upload_outputs,
        show_progress="upload"
    )

    # NOVO: Função de toggle que usa o estado do livro
    def toggle_all_chapters(current_selection: List[int], book_data: Dict):
        """Seleciona ou deseleciona todos os capítulos usando os dados do book_data_state."""
        if not book_data or "chapter_choices_for_ui" not in book_data:
            gr.Warning("Please upload an EPUB file first.")
            return gr.update(), gr.update() # Não faz nada se o estado estiver vazio

        print("--- TOGGLE BUTTON CLICKED ---")
        print(f"Accessing book data from state. Title: {book_data.get('title')}")

        all_chapter_indices = [choice[1] for choice in book_data["chapter_choices_for_ui"]]
        if not all_chapter_indices:
            return gr.update(), gr.update(value=t['no_chapters_found'])

        if len(current_selection) < len(all_chapter_indices):
            # Se nem todos estiverem selecionados, seleciona todos
            return gr.update(value=all_chapter_indices), gr.update(value=t['deselect_all_btn'])
        else:
            # Se todos estiverem selecionados, deseleciona todos
            return gr.update(value=[]), gr.update(value=t['deselect_all_btn'])

    # NOVO: Evento de clique do botão de toggle que passa o estado como entrada
    toggle_chapters_btn.click(
        fn=toggle_all_chapters,
        inputs=[chapters_selector, book_data_state],
        outputs=[chapters_selector, toggle_chapters_btn]
    )

    submit_btn.click(
        fn=gradio_translate_epub,
        inputs=[
            epub_upload_btn,
            model_name_input,
            lang_from_dropdown,
            lang_to_dropdown,
            chapters_selector
        ],
        outputs=[output_file_display],
    )

if __name__ == "__main__":
    app.queue()
    app.launch(debug=True)