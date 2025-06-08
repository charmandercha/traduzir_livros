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

# --- Lógica Principal de Tradução (Revisada) ---

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
        # print(f"DEBUG: Sending to LLM (model: {model_name}, from: {from_lang}, to: {to_lang}):\n{html_fragment[:300]}...")
        print(f"TRANSLATE_CHUNK: Enviando para o modelo {model_name}. De: {from_lang}, Para: {to_lang}. Tamanho do fragmento: {len(html_fragment)} chars.")
        print(f"TRANSLATE_CHUNK: Conteúdo do fragmento (primeiros 300 chars):\n{html_fragment[:300]}")
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.2,
            messages=[
                {'role': 'system', 'content': system_prompt(from_lang, to_lang)},
                {'role': 'user', 'content': html_fragment},
            ],
            timeout=180 # Timeout aumentado para fragmentos maiores ou LLMs mais lentas
        )
        translated_text = response.choices[0].message.content
        translated_text = re.sub(r'<think>.*?</think>', '', translated_text, flags=re.DOTALL).strip()



        # print(f"DEBUG: Received from LLM:\n{translated_text[:300]}...")
        print(f"TRANSLATE_CHUNK: Recebido do modelo {model_name}. Tamanho da tradução: {len(translated_text)} chars.")
        print(f"TRANSLATE_CHUNK: Conteúdo traduzido (primeiros 300 chars):\n{translated_text[:300]}")
        translated_text = translated_text.replace('<think>', '').replace('</think>', '')
        print(f"TRANSLATE_CHUNK: Fragmento traduzido final (após limpeza):\n{translated_text}")
        print(translated_text)
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
    """
    Itera sobre elementos de bloco no BeautifulSoup object, traduz seu conteúdo HTML
    e substitui o elemento original pelo traduzido.
    """
    # Elementos de bloco comuns. Adicionar mais conforme necessário (ex: 'blockquote', 'table', 'figure')
    # A ordem pode importar se houver aninhamento e você quiser traduzir o mais externo primeiro
    # ou o mais interno. Iterar sobre todos e deixar a LLM lidar com o contexto é geralmente ok.
    block_selectors = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'div', 'caption', 'td', 'th', 'dt', 'dd']
    
    elements_to_translate = []
    for selector in block_selectors:
        elements_to_translate.extend(soup.find_all(selector))

    # Remover duplicatas se um elemento corresponder a múltiplos seletores (improvável com esta lista)
    # e manter a ordem do documento (BeautifulSoup geralmente faz isso)
    # Se elementos estiverem aninhados (ex: div dentro de div), ambos serão encontrados.
    # A tradução do elemento externo incluirá o interno (que pode ou não ser traduzido novamente
    # dependendo da estratégia).
    # Para evitar retradução, pode-se marcar elementos já processados ou traduzir apenas
    # os nós de texto mais profundos. A abordagem atual traduz o HTML do bloco.

    # Uma estratégia para evitar retradução de blocos aninhados:
    # Processar apenas os elementos que não têm um pai já na lista.
    # No entanto, para simplificar e dar mais contexto à LLM, traduzir o bloco inteiro é mais direto.
    
    # Se nenhum elemento de bloco for encontrado, tenta traduzir nós de texto soltos dentro do body.
    if not elements_to_translate:
        all_text_nodes_in_body = soup.body.find_all(string=True, recursive=False) if soup.body else []
        temp_elements = []
        for text_node in all_text_nodes_in_body:
            if text_node.strip():
                # Envolve o texto em um span para que possa ser substituído como um 'elemento'
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

        # Verifica se o elemento ainda está na árvore (pode ter sido removido/substituído se era filho de outro bloco já traduzido)
        if not element_tag.parent:
            print(f"TRANSLATE_HTML_BLOCKS: Pulando elemento {element_tag.name} (bloco {i+1}/{num_blocks}) pois não está mais na árvore (provavelmente parte de um pai já traduzido).")
            continue

        original_html_fragment = str(element_tag) # Serializa o elemento inteiro (incluindo a tag externa)

        if not original_html_fragment.strip():
            continue

        print(f"TRANSLATE_HTML_BLOCKS: Traduzindo bloco {i+1}/{num_blocks} do capítulo '{chapter_name}' (tag: {element_tag.name}, ID do elemento na lista: {i}). Tamanho original: {len(original_html_fragment)} chars.")
        translated_html_str = translate_chunk(client, original_html_fragment, model_name, from_lang, to_lang)

        if translated_html_str and translated_html_str.strip() != original_html_fragment.strip():
            print(f"TRANSLATE_HTML_BLOCKS: Bloco {i+1}/{num_blocks} ('{element_tag.name}') traduzido. Tentando substituir no DOM. Tamanho traduzido: {len(translated_html_str)} chars.")
            try:
                # Parse o fragmento traduzido. A LLM deve retornar um fragmento HTML correspondente.
                translated_soup_fragment = BeautifulSoup(translated_html_str, 'html.parser')
                
                new_element = None
                # A LLM pode retornar um documento HTML completo ou apenas o fragmento.
                if translated_soup_fragment.body and translated_soup_fragment.body.contents:
                    if len(translated_soup_fragment.body.contents) == 1 and isinstance(translated_soup_fragment.body.contents[0], Tag):
                        new_element = translated_soup_fragment.body.contents[0]
                    else: # Múltiplos elementos no body, ou texto solto. Tenta usar o body como container se for o caso.
                          # Isso é menos ideal. Espera-se que a LLM retorne um elemento principal.
                          # Se for uma lista de elementos, eles serão inseridos sequencialmente.
                          # Isso pode quebrar a estrutura se o original era um único elemento.
                          # Para ser seguro, se o original era um Tag, tentamos pegar o primeiro Tag do fragmento.
                        new_element = translated_soup_fragment.body.find(lambda tag: isinstance(tag, Tag), recursive=False)
                        if not new_element: # Se só texto, ou estrutura inesperada.
                            # Envolve em um span para preservar o texto
                            temp_span = soup.new_tag("span", attrs={"data-translated-wrapper": "true"})
                            for content_item in translated_soup_fragment.body.contents:
                                temp_span.append(content_item.extract()) # Mover conteúdo
                            new_element = temp_span

                elif translated_soup_fragment.contents and isinstance(translated_soup_fragment.contents[0], Tag):
                    new_element = translated_soup_fragment.contents[0]
                
                if new_element:
                    element_tag.replace_with(new_element)
                else:
                    # Se não conseguiu extrair um new_element válido mas há tradução,
                    # tenta uma substituição mais bruta (menos seguro)
                    # Isso pode acontecer se a LLM retornar apenas texto sem tags de invólucro.
                    # Se element_tag era um wrapper de texto (data-text-node), isso é esperado.
                    if element_tag.name == "span" and element_tag.get("data-text-node") == "true":
                        element_tag.string = translated_soup_fragment.get_text() # substitui só o texto
                    else:
                        gr.Warning(f"Translated content for a block in '{chapter_name}' was not a single valid HTML element. Inserting as text if possible or keeping original.")
                        print(f"TRANSLATE_HTML_BLOCKS: Conteúdo traduzido para o bloco {i+1}/{num_blocks} em '{chapter_name}' não era um elemento HTML único válido. Tentando inserir como texto ou manter o original.")
                        # Tenta substituir pelo texto do fragmento se o original era um bloco.
                        # Isso pode perder a formatação do bloco.
                        element_tag.string = translated_soup_fragment.get_text()


            except Exception as e:
                print(f"TRANSLATE_HTML_BLOCKS: ERRO ao parsear ou substituir bloco HTML traduzido no capítulo '{chapter_name}'. Bloco {i+1}/{num_blocks} (tag: {element_tag.name}). Erro: {e}")
                traceback.print_exc()
                gr.Warning(f"Could not process translated block in '{chapter_name}': {type(e).__name__}. Original content kept for this block.")
        # else: O chunk não foi traduzido ou é igual ao original, nada a fazer.

# --- Funções Auxiliares Gradio ---

def get_epub_chapters_details(epub_path: str) -> List[Dict[str, Any]]:
    print(f"GET_EPUB_CHAPTERS_DETAILS: Iniciando extração de detalhes dos capítulos para: {epub_path}")
    try:
        book = epub.read_epub(epub_path)
        chapters = []
        for i, item in enumerate(book.get_items_of_type(ebooklib.ITEM_DOCUMENT)):
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text_content = soup.get_text()
            # Tenta pegar um título do h1, h2 ou nome do arquivo
            title_tag = soup.find(['h1', 'h2'])
            chapter_display_name = title_tag.get_text(strip=True) if title_tag else item.get_name()
            if not chapter_display_name:  chapter_display_name = f"Chapter Document {i+1}"

            chapters.append({
                "id": item.get_name(), # ID interno do item
                "name": chapter_display_name,
                "char_count": len(text_content),
                "preview": text_content[:200].strip().replace('\n', ' ') # Preview curto
            })
            print(f"GET_EPUB_CHAPTERS_DETAILS: Detalhes de {len(chapters)} capítulos extraídos com sucesso para: {epub_path}")
        return chapters
    except Exception as e:
        print(f"GET_EPUB_CHAPTERS_DETAILS: ERRO ao ler EPUB para detalhes dos capítulos. Caminho: {epub_path}. Erro: {e}")
        traceback.print_exc()
        return []

def parse_epub_metadata_and_chapters(epub_file_obj: Optional[tempfile._TemporaryFileWrapper]):
    if epub_file_obj is None: # Chamado quando o upload é limpo
        print("PARSE_EPUB_METADATA: Upload limpo. Resetando campos da UI.")
        return (
            gr.update(choices=[], value=[], label="Chapters to Translate", interactive=False), # chapters_selector
            gr.update(value="auto"), # lang_from_dropdown
            gr.update(value="PT-BR"), # lang_to_dropdown
            gr.update(value=""), # epub_title_display
            gr.update(value=""), # epub_author_display
            gr.update(value=""), # chapter_count_display
            gr.update(value=[])  # available_chapter_choices_state (para Select All)
        )

    epub_path = epub_file_obj.name # type="filepath" fornece o caminho
    file_size_mb = os.path.getsize(epub_path) / (1024 * 1024)
    print(f"PARSE_EPUB_METADATA: Processando arquivo: {epub_path}, Tamanho: {file_size_mb:.2f} MB")
    try:
        file_type = magic.from_file(epub_path, mime=True)
        if file_type != 'application/epub+zip':
            gr.Warning(f"Uploaded file MIME type ({file_type}) is not 'application/epub+zip'. Processing will continue but may fail.")
            print(f"PARSE_EPUB_METADATA: Tipo MIME verificado: {file_type}")
    except Exception as e:
        gr.Warning(f"Could not verify file MIME type using python-magic: {e}. Ensure 'python-magic' and its dependencies are correctly installed.")
        print(f"PARSE_EPUB_METADATA: ERRO ao verificar tipo MIME: {e}")


    if file_size_mb > MAX_EPUB_SIZE_MB:
        gr.Error(f"EPUB file size ({file_size_mb:.2f} MB) exceeds the limit of {MAX_EPUB_SIZE_MB} MB.")
        print(f"PARSE_EPUB_METADATA: ERRO - Tamanho do arquivo ({file_size_mb:.2f} MB) excede o limite de {MAX_EPUB_SIZE_MB} MB.")
        return (gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(value=[]))


    try:
        book = epub.read_epub(epub_path)
    except Exception as e:
        gr.Error(f"Error reading EPUB file: {e}. It might be corrupted or not a valid EPUB.")
        traceback.print_exc()
        return (gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(value=[]))

    title_meta = book.get_metadata('DC', 'title')
    title_str = title_meta[0][0] if title_meta and title_meta[0] else "Unknown Title"
    
    authors_meta = book.get_metadata('DC', 'creator')
    author_str = ', '.join([a[0] for a in authors_meta]) if authors_meta else "Unknown Author"

    chapters_details = get_epub_chapters_details(epub_path) # Lista de dicts
    num_chapters = len(chapters_details)
    
    # Choices para o CheckboxGroup: (label, value_que_sera_retornado_quando_selecionado)
    # O valor será o índice do capítulo na lista de todos os documentos do EPUB.
    chapter_choices_for_ui = []
    for i, ch_detail in enumerate(chapters_details):
        label = f"Ch. {i+1}: {ch_detail['name']} ({ch_detail['char_count']} chars) - \"{ch_detail['preview']}...\""
        chapter_choices_for_ui.append((label, i)) # (label, index)

    detected_lang_code = "auto"
    try:
        sample_text = " ".join([ch['preview'] for ch in chapters_details[:5]]) # Amostra dos primeiros capítulos
        if sample_text.strip():
            detected_lang_code = detect(sample_text.strip())
            detected_lang_code = detected_lang_code.split('-')[0].upper()
            
            is_in_list = any(detected_lang_code == lang_tuple[1] for lang_tuple in COMMON_LANGUAGES)
            if not is_in_list: # Tenta correspondência parcial (ex: EN de EN-GB)
                 potential_match = next((lang_tuple[1] for lang_tuple in COMMON_LANGUAGES if detected_lang_code.startswith(lang_tuple[1])), None)
                 if potential_match:
                     detected_lang_code = potential_match
                 else:
                    gr.Info(f"Detected language '{detected_lang_code}' not in predefined list. Defaulting source to 'Auto-Detect'.")
                    detected_lang_code = "auto"
            else:
                gr.Info(f"Detected source language: {detected_lang_code}")
        else:
            detected_lang_code = "auto"
    except Exception as e:
        # LangDetectException ou outra
        gr.Warning(f"Language detection failed: {type(e).__name__}. Defaulting to 'Auto-Detect'.")
        detected_lang_code = "auto"

    from_lang_value = detected_lang_code if detected_lang_code != "auto" else "auto"

    return (
        gr.update(choices=chapter_choices_for_ui, value=list(range(num_chapters)), label=f"Chapters to Translate ({num_chapters} found)", interactive=True),
        gr.update(value=from_lang_value),
        gr.update(), # lang_to_dropdown (sem mudança)
        gr.update(value=title_str),
        gr.update(value=author_str),
        gr.update(value=f"{num_chapters} chapter documents found in the EPUB."),
        gr.update(value=chapter_choices_for_ui) # Para o available_chapter_choices_state
    )


def gradio_translate_epub(
    epub_file_obj: tempfile._TemporaryFileWrapper, # Vem do gr.UploadButton
    model_name: str,
    from_lang_ui: str,
    to_lang_ui: str,
    selected_chapter_indices: List[int], # Lista de ÍNDICES dos capítulos selecionados
    progress=gr.Progress(track_tqdm=True)
):
    if not epub_file_obj:
        gr.Error("Please upload an EPUB file first.")
        return None # Retorna None para o gr.File de output
    if not model_name:
        gr.Error("Please enter or select an Ollama model name.")
        return None
    if not selected_chapter_indices: # selected_chapter_indices é uma lista de índices
        gr.Warning("No chapters selected for translation. Nothing to do.")
        return None

    input_epub_path = epub_file_obj.name

    final_from_lang = from_lang_ui
    if final_from_lang == "auto":
        # Tenta uma detecção rápida se ainda for 'auto'
        try:
            temp_book_for_lang_detect = epub.read_epub(input_epub_path)
            sample_text = ""
            for item_idx, item_doc in enumerate(temp_book_for_lang_detect.get_items_of_type(ebooklib.ITEM_DOCUMENT)):
                if item_idx < 5: # Amostra dos primeiros 5 capítulos/documentos
                    soup = BeautifulSoup(item_doc.get_content(), 'html.parser')
                    sample_text += soup.get_text(separator=' ', strip=True)[:200] + " "
                if len(sample_text) > 1000: break
            
            if sample_text.strip():
                detected = detect(sample_text.strip()).upper().split('-')[0]
                if any(detected == lang_tuple[1] for lang_tuple in COMMON_LANGUAGES if lang_tuple[1] != "auto"):
                    final_from_lang = detected
                    gr.Info(f"Auto-detected source language for translation as: {final_from_lang}")
                else: # Fallback
                    final_from_lang = "EN" 
                    gr.Info(f"Could not robustly auto-detect source language from EPUB content. Assuming '{final_from_lang}'.")
            else: # Fallback
                final_from_lang = "EN"
                gr.Info(f"Not enough text in EPUB to auto-detect source language. Assuming '{final_from_lang}'.")
        except Exception as e: # Fallback
            final_from_lang = "EN"
            gr.Warning(f"Error during pre-translation language auto-detection: {type(e).__name__}. Assuming '{final_from_lang}'.")

    try:
        client = OpenAI(
            base_url=DEFAULT_OLLAMA_BASE_URL,
            api_key=DEFAULT_OLLAMA_API_KEY,
        )
        # Testar conexão com um chamado simples (opcional, mas bom para feedback rápido)
        try:
            client.models.list() # Exemplo de chamado leve
        except Exception as conn_err:
            gr.Error(f"Failed to connect or communicate with Ollama server at {DEFAULT_OLLAMA_BASE_URL}. Error: {type(conn_err).__name__} - {conn_err}")
            return None

        book = epub.read_epub(input_epub_path)
        all_document_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        
        # Mapear os selected_chapter_indices para os itens reais do livro
        chapters_to_process_items = []
        for chap_idx in selected_chapter_indices:
            if 0 <= chap_idx < len(all_document_items):
                chapters_to_process_items.append(all_document_items[chap_idx])
            else:
                gr.Warning(f"Invalid chapter index {chap_idx} encountered. Skipping.")
        
        if not chapters_to_process_items:
            gr.Error("No valid chapters selected or found for processing.")
            return None

        total_chapters_for_progress = len(chapters_to_process_items)
        progress(0, desc="Starting translation...")

        for i, item_to_translate in enumerate(chapters_to_process_items):
            # Obter o nome do capítulo para o progresso (usa o ID do item se nome não disponível)
            item_id_or_name = item_to_translate.get_name() if item_to_translate.get_name() else f"Document Index {all_document_items.index(item_to_translate)}"
            
            # Atualiza o progresso geral por capítulo
            progress_desc = f"Translating Ch. {i+1}/{total_chapters_for_progress} ('{item_id_or_name}')..."
            progress( (i) / total_chapters_for_progress, desc=progress_desc)
            
            print(f"Processing chapter {i+1}/{total_chapters_for_progress}: {item_id_or_name}")
            
            try:
                original_content_bytes = item_to_translate.get_content()
                soup = BeautifulSoup(original_content_bytes, 'html.parser')

                # Função para progresso de blocos dentro do capítulo (opcional para UI principal)
                def chapter_block_progress_updater(block_progress_ratio):
                    # Atualiza a descrição da barra de progresso principal com detalhes do bloco
                    # Isso pode ser muito "barulhento" na UI. Melhor logar no console.
                    # progress( (i + block_progress_ratio) / total_chapters_for_progress, desc=f"{progress_desc} (block {int(block_progress_ratio*100)}%)")
                    print(f"\tProgress for '{item_id_or_name}': {int(block_progress_ratio*100)}% of blocks translated.")

                translate_html_block_elements(
                    client, soup, model_name, final_from_lang, to_lang_ui, item_id_or_name,
                    # progress_callback_chapter_blocks=chapter_block_progress_updater # Descomente para progresso mais granular no console
                )
                
                item_to_translate.set_content(str(soup).encode('utf-8'))
            except Exception as e_chap:
                gr.Warning(f"Failed to translate or process chapter '{item_id_or_name}': {type(e_chap).__name__} - {e_chap}. It may be left untranslated or partially translated.")
                traceback.print_exc()
                # Opcional: reverter para conteúdo original do capítulo se falhar
                # item_to_translate.set_content(original_content_bytes) 

        progress(1, desc="Translation complete! Finalizing EPUB...")

        # Salvar o EPUB traduzido em um arquivo temporário que o Gradio possa servir
        with tempfile.NamedTemporaryFile(delete=False, suffix=".epub", prefix="translated_") as tmp_output_file:
            output_epub_path = tmp_output_file.name
        
        epub.write_epub(output_epub_path, book, {})
        print(f"GRADIO_TRANSLATE_EPUB: EPUB traduzido salvo em: {output_epub_path}")
        gr.Info("EPUB translation successful!")
        return output_epub_path # Caminho para o arquivo temporário

    except Exception as e_main:
        gr.Error(f"An unexpected error occurred: {type(e_main).__name__} - {e_main}")
        traceback.print_exc()
        return None

# --- Interface Gradio ---
css = """
.contain{
max-width: 660px;
margin: 0 auto;
}
.detalhes .form{
border: none;
}
.detalhes .form{
border: none;
}
.BookDetails{
padding: 0;
}
.meuBloco{
border-radius: 10px;
}
"""

# with gr.Blocks(theme=gr.themes.Soft(primary_hue=gr.themes.colors.blue, secondary_hue='gr.themes.colors.sky'), css=css) as app:
with gr.Blocks(theme='earneleh/paris', css=css) as app:

    gr.Markdown("## 📖 EPUB Translator with Ollama")
    gr.Markdown("Upload an EPUB, select model, languages, and chapters, then translate using a local Ollama model.")

    # State para armazenar as escolhas de capítulos disponíveis para os botões Select All/None
    available_chapter_choices_state = gr.State([])

    with gr.Row():
        with gr.Column(scale=3, elem_classes=['newBg']): # Coluna da esquerda um pouco maior
            gr.Markdown("### 1. Upload & Configure EPUB")
            epub_upload_btn = gr.UploadButton(
                "Click to Upload EPUB",
                file_types=[".epub"],
                type="filepath" # CORRIGIDO: de "file" para "filepath"
            )
            
            gr.Markdown("### 1. Translation Settings")
            model_name_input = gr.Textbox(
                label="Ollama Model Name (the model that will do the translation)",
                elem_classes="meuBloco",
                placeholder="e.g., llama3, mistral",
                value=DEFAULT_MODEL
            )
            # gr.Dataset(components=[model_name_input], samples=[[s] for s in SUGGESTED_MODELS], label="Suggested Ollama Models")

            with gr.Row(elem_classes="small_gap meuBloco"):
                lang_from_dropdown = gr.Dropdown(
                        label="From Language", choices=COMMON_LANGUAGES, value="auto", elem_classes="meuBloco title me-1"
                    )
                lang_to_dropdown = gr.Dropdown(
                        label="To Language",
                        choices=[(name, code) for name, code in COMMON_LANGUAGES if code != "auto"],
                        value="PT-BR",
                        elem_classes="meuBloco ms-1"
                    )
            
        # with gr.Column(scale=3): # Coluna da direita maior para a lista de capítulos
            with gr.Accordion(label="Choose chapters to translate (default = all)",elem_classes="meuBloco detalhes", open=False):
                with gr.Row():
                    with gr.Column(scale=8, elem_classes=['newBg']):
                        gr.Markdown("### 3. Select Chapters for Translation")
                    with gr.Column(scale=3, elem_classes=['newBg']):
                        toggle_chapters_btn = gr.Button("Deselect All Chapters")
                chapters_selector = gr.CheckboxGroup(
                    label="Chapters to Translate", choices=[], value=[], interactive=False,elem_classes="meuBloco"
                    # elem_classes="gr-checkboxgroup-scrollable" # Adicione CSS para scroll se necessário
                )
            with gr.Accordion(label="Details about the book like title, description & etc (default=the original content)",elem_classes="meuBloco detalhes",  open=False):
                epub_title_display = gr.Textbox(label="Book Title", elem_classes="BookDetails", interactive=False, lines=1)
                epub_author_display = gr.Textbox(label="Book Author", elem_classes="BookDetails", interactive=False, lines=1)
                chapter_count_display = gr.Textbox(label="EPUB Structure Info", elem_classes="BookDetails", interactive=False, lines=1)
            gr.Markdown("### 4. Translate & Download")
            submit_btn = gr.Button("🌍 Translate Selected Chapters", variant="primary", scale=2)
            
            progress_bar = gr.Progress()
            output_file_display = gr.File(label="Download Translated EPUB", interactive=False)

    # --- Eventos Gradio ---
    upload_outputs = [
        chapters_selector,
        lang_from_dropdown,
        lang_to_dropdown,
        epub_title_display,
        epub_author_display,
        chapter_count_display,
        available_chapter_choices_state # Atualiza o state com as escolhas
    ]

    epub_upload_btn.upload(
        fn=parse_epub_metadata_and_chapters,
        inputs=[epub_upload_btn],
        outputs=upload_outputs,
        show_progress="upload" 
    )

    def deselect_all_chapters():
        return gr.update(value=[])
    
    def toggle_all_chapters(current_selection, all_choices):
        
        all_values = [choice[1] for choice in all_choices]
        print(all_choices)
        if not current_selection or len(current_selection) < len(all_values):
            return gr.update(value=all_values), gr.update(value="Deselect All Chapters")
        else:
            return gr.update(value=[]), gr.update(value="Select All Chapters")
    
   
    toggle_chapters_btn.click(
        fn=toggle_all_chapters,
        inputs=[chapters_selector, available_chapter_choices_state],
        outputs=[chapters_selector, toggle_chapters_btn]
    )

    submit_btn.click(
        fn=gradio_translate_epub,
        inputs=[
            epub_upload_btn,
            model_name_input,
            lang_from_dropdown,
            lang_to_dropdown,
            chapters_selector # Passa a lista de índices selecionados
        ],
        outputs=[output_file_display],
    )

if __name__ == "__main__":
    app.queue() 
    app.launch(debug=True) # share=True para expor publicamente (com cautela!)
