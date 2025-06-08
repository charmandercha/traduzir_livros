translations = {
    "en": {
        # --- UI Elements ---
        "app_title": "## 📖 EPUB Translator with Ollama",
        "app_subtitle": "Upload an EPUB, select model, languages, and chapters, then translate using a local Ollama model.",
        
        "section_1_title": "### 1. Upload & Configure EPUB",
        "upload_button_text": "Click to Upload EPUB",
        
        "section_2_title": "### 2. Translation Settings",
        "model_name_label": "Ollama Model Name",
        "model_name_placeholder": "e.g., llama3, mistral",
        "from_language_label": "From Language",
        "to_language_label": "To Language",

        "chapters_accordion_label": "Choose chapters to translate (default = all)",
        "section_3_title": "### 3. Select Chapters for Translation",
        "deselect_all_btn": "Deselect All Chapters",
        "select_all_btn": "Select All Chapters",
        "chapters_selector_label": "Chapters to Translate",
        
        "details_accordion_label": "Details about the book",
        "book_title_label": "Book Title",
        "book_author_label": "Book Author",
        "epub_structure_info_label": "EPUB Structure Info",

        "section_4_title": "### 4. Translate & Download",
        "translate_button_text": "🌍 Translate Selected Chapters",
        "download_label": "Download Translated EPUB",
        
        # --- Dynamic & Status Messages ---
        "chapters_selector_label_count": "Chapters to Translate ({num_chapters} found)",
        "epub_structure_info_value": "{num_chapters} chapter documents found in the EPUB.",
        "progress_starting": "Starting translation...",
        "progress_translating_chapter": "Translating Ch. {i}/{total} ('{name}')...",
        "progress_complete": "Translation complete! Finalizing EPUB...",
        "no_chapters_found": "No Chapters Found",

        # --- Notifications (Info, Warning, Error) ---
        "info_lang_detected": "Auto-detected source language for translation as: {lang}",
        "info_lang_detection_failed": "Could not robustly auto-detect source language from EPUB content. Assuming '{lang}'.",
        "info_lang_not_enough_text": "Not enough text in EPUB to auto-detect source language. Assuming '{lang}'.",
        "info_translation_successful": "EPUB translation successful!",
        
        "warning_no_chapters_selected": "No chapters selected for translation. Nothing to do.",
        "warning_upload_epub_first": "Please upload an EPUB file first.",
        "warning_mime_type": "Uploaded file MIME type ({file_type}) is not 'application/epub+zip'. Processing will continue but may fail.",
        "warning_language_detection_failed": "Language detection failed: {error_type}. Defaulting to 'Auto-Detect'.",
        
        "error_no_epub_uploaded": "Please upload an EPUB file first.",
        "error_no_model": "Please enter or select an Ollama model name.",
        "error_epub_size_exceeded": "EPUB file size ({file_size_mb:.2f} MB) exceeds the limit of {max_size} MB.",
        "error_reading_epub": "Error reading EPUB file: {error}. It might be corrupted or not a valid EPUB.",
        "error_ollama_connection": "Failed to connect to Ollama server at {url}. Error: {error_type} - {error}",
        "error_no_valid_chapters": "No valid chapters selected or found for processing.",
        "error_unexpected": "An unexpected error occurred: {error_type} - {error}",
    },
    "pt": {
    # --- UI Elements ---
    "app_title": "## 📖 Tradutor de EPUB com Ollama",
    "app_subtitle": "Faça upload de um EPUB, selecione modelo, idiomas e capítulos, e então traduza usando um modelo Ollama local.",
    
    "section_1_title": "### 1. Carregar & Configurar EPUB",
    "upload_button_text": "Clique para Fazer Upload do EPUB",
    
    "section_2_title": "### 2. Configurações de Tradução",
    "model_name_label": "Nome do Modelo Ollama",
    "model_name_placeholder": "ex.: llama3, mistral",
    "from_language_label": "Idioma de Origem",
    "to_language_label": "Idioma de Destino",

    "chapters_accordion_label": "Escolha os capítulos a serem traduzidos (padrão = todos)",
    "section_3_title": "### 3. Selecione Capítulos para Tradução",
    "deselect_all_btn": "Desmarcar Todos os Capítulos",
    "select_all_btn": "Marcar Todos os Capítulos",
    "chapters_selector_label": "Capítulos a Serem Traduzidos",
    
    "details_accordion_label": "Detalhes sobre o livro",
    "book_title_label": "Título do Livro",
    "book_author_label": "Autor do Livro",
    "epub_structure_info_label": "Informações sobre a Estrutura do EPUB",

    "section_4_title": "### 4. Traduzir & Baixar",
    "translate_button_text": "🌍 Traduzir Capítulos Selecionados",
    "download_label": "Baixar EPUB Traduzido",
    
    # --- Dynamic & Status Messages ---
    "chapters_selector_label_count": "Capítulos a Serem Traduzidos ({num_chapters} encontrados)",
    "epub_structure_info_value": "{num_chapters} documentos de capítulo encontrados no EPUB.",
    "progress_starting": "Iniciando tradução...",
    "progress_translating_chapter": "Traduzindo Cap. {i}/{total} ('{name}')...",
    "progress_complete": "Tradução concluída! Finalizando EPUB...",
    "no_chapters_found": "Nenhum Capítulo Encontrado",

    # --- Notifications (Info, Warning, Error) ---
    "info_lang_detected": "Idioma de origem detectado automaticamente: {lang}",
    "info_lang_detection_failed": "Não foi possível detectar automaticamente o idioma de origem do EPUB. Assumindo '{lang}'.",
    "info_lang_not_enough_text": "Texto insuficiente no EPUB para detectar automaticamente o idioma de origem. Assumindo '{lang}'.",
    "info_translation_successful": "Tradução do EPUB concluída com sucesso!",
    
    "warning_no_chapters_selected": "Nenhum capítulo selecionado para tradução. Nada a fazer.",
    "warning_upload_epub_first": "Por favor, faça o upload de um arquivo EPUB primeiro.",
    "warning_mime_type": "Tipo MIME do arquivo enviado ({file_type}) não é 'application/epub+zip'. O processamento continuará, mas pode falhar.",
    "warning_language_detection_failed": "Falha na detecção do idioma: {error_type}. Usando 'Auto-Detectar' como padrão.",
    
    "error_no_epub_uploaded": "Por favor, faça o upload de um arquivo EPUB primeiro.",
    "error_no_model": "Por favor, insira ou selecione um nome de modelo Ollama.",
    "error_epub_size_exceeded": "O tamanho do arquivo EPUB ({file_size_mb:.2f} MB) excede o limite de {max_size} MB.",
    "error_reading_epub": "Erro ao ler o arquivo EPUB: {error}. Pode estar corrompido ou não ser um EPUB válido.",
    "error_ollama_connection": "Falha ao conectar ao servidor Ollama em {url}. Erro: {error_type} - {error}",
    "error_no_valid_chapters": "Nenhum capítulo válido selecionado ou encontrado para processamento.",
    "error_unexpected": "Ocorreu um erro inesperado: {error_type} - {error}",
}
    # Você pode adicionar outras línguas aqui no futuro
    # "pt_br": {
    #     "app_title": "## 📖 Tradutor de EPUB com Ollama",
    #     ...
    # }
}