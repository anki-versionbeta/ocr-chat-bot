document.addEventListener("DOMContentLoaded", () => {
    // --- Global State ---
    window.selectedFilenames = window.selectedFilenames || new Set();
    window.sourceSelections = window.sourceSelections || {};
    let isFirstModalOpen = true;
    
    // Maintain selection state per source
    let currentSource = null;
    let lastSource = null;
    let droppedFiles = null;
//     let droppedFolder = null;
    
    let documents = [];
    
    let loadingIndex = 0;
    let loadingInterval = null;
    let isLoadingTextActive = false;


    // --- DOM Elements ---
    const sourceSelect = document.getElementById('sourceSelect');
    const modal = document.getElementById('sourceModal');
    const documentModal = document.getElementById('documentModal');
    const chatContainer = document.getElementById('chatContainer');
    const uploadProgress = document.getElementById('uploadProgress');
    const progressBar = uploadProgress.querySelector('div');
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const toggle = document.getElementById('toggleType');
    const documentFile = document.getElementById('documentFile');
    const documentFolder = document.getElementById('documentFolder');
    const uploadBtn = document.getElementById('uploadBtn');
    const uploadFolder = document.getElementById('uploadFolderBtn');
    const fileInput = document.getElementById('fileInput');
    const folderInput = document.getElementById('folderInput');
    const browse_file = document.getElementById('browse_file');
    const browse_folder= document.getElementById('browse_folder')
    const selectedFilesDiv = document.getElementById('selectedFiles');
    const viewFiles = document.getElementById("viewFiles");
    const loaderContainer = document.getElementById('loader-container');
    const loadingText = document.getElementById("loadingText");
    const clearSession = document.getElementById("clearSession");
   
    // --- Loading Messages for Uploading files --
    const loadingMessages = [
          "Processing file contents...",
          "Extracting metadata...",
          "Handling Document upload...",
        ];


    // --- UI Initialization ---
    fetchSources();
    setUploadMode(toggle.checked);

    // --- Event Listeners ---
    toggle.addEventListener('change', () => setUploadMode(toggle.checked));

    sourceSelect.addEventListener('change', () => {
        handleSourceChange();
        
        modal.classList.remove('hidden');
        const closeBtn = modal.querySelector('button');
        if (closeBtn) {
            closeBtn.onclick = () => modal.classList.add('hidden');
        }
        documentFile.addEventListener('change', checkUploadButton);
        documentFolder.addEventListener('change', checkUploadFolderButton);
        uploadBtn.addEventListener('click', handleDocumentUpload);
        uploadFolder.addEventListener('click', handleFolderUpload);
    });

    documentFile.addEventListener('click', e => { if (e.target === documentFile) fileInput.click(); });
    documentFolder.addEventListener('click', e => { if (e.target === documentFolder) folderInput.click(); });
    documentFile.addEventListener('dragover', e => { e.preventDefault(); documentFile.classList.add('ring-2', 'ring-[#1db77c]'); });
    documentFile.addEventListener('dragleave', () => documentFile.classList.remove('ring-2', 'ring-[#1db77c]'));
    documentFile.addEventListener('drop', e => { e.preventDefault(); documentFile.classList.remove('ring-2', 'ring-[#1db77c]'); droppedFiles=e.dataTransfer.files; displaySelectedFiles(droppedFiles, false); checkUploadButton()});
    documentFolder.addEventListener('dragover', e => { e.preventDefault(); documentFolder.classList.add('ring-2', 'ring-[#1db77c]'); });
    documentFolder.addEventListener('dragleave', () => documentFolder.classList.remove('ring-2', 'ring-[#1db77c]'));
//     documentFolder.addEventListener('drop', e => { e.preventDefault(); documentFolder.classList.remove('ring-2', 'ring-[#1db77c]'); droppedFolder=e.dataTransfer.files;  displaySelectedFiles(droppedFolder, true); });
    fileInput.addEventListener('change', e => displaySelectedFiles(e.target.files, false));
    folderInput.addEventListener('change', e => displaySelectedFiles(e.target.files, true));
    document.getElementById('browse_file').addEventListener('click', e => { e.stopPropagation(); fileInput.click(); });
    document.getElementById('browse_folder').addEventListener('click', e => { e.stopPropagation(); folderInput.click(); });

    clearSession.addEventListener("click", () => {
        Swal.fire({
                    title: 'Are you sure ?',
                    html: `Confirm to delete the current Session History.`,
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonText: 'Yes, delete it!',
                    cancelButtonText: 'Cancel'
                }).then(result => {
                    if (result.isConfirmed) clearSessionHistory();
                });
            });
    
    
    messageInput.addEventListener('keypress', e => {
        if (e.key === 'Enter') {
            const message = messageInput.value.trim();
            if (message) {
                sendMessage(message);
                messageInput.value = '';
            }
        }
    });
    sendBtn.addEventListener('click', () => {
        const message = messageInput.value.trim();
        if (message) {
            sendMessage(message);
            messageInput.value = '';
        }
    });
    
   
    // --- Functions ---
    
    function setUploadMode(isFolder) {
        documentFile.style.display = isFolder ? 'none' : 'block';
        documentFolder.style.display = isFolder ? 'block' : 'none';
        uploadBtn.style.display = isFolder ? 'none' : 'block';
        uploadFolder.style.display = isFolder ? 'block' : 'none';
    }

    async function fetchSources() {
        try {
            const response = await fetch(getWebAppBackendUrl("/list_sources"), { method: "GET", headers: { 'Content-Type': 'application/json' } });
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            const data = await response.json();
            sourceSelect.innerHTML = '<option value="" selected disabled>Select a source</option>';
            if (data.sources && Array.isArray(data.sources)) {
                data.sources.forEach(source => {
                    const option = document.createElement('option');
                    if (typeof source === 'string') {
                        option.value = source;
                        option.textContent = source;
                    } else if (source && typeof source === 'object' && source.source) {
                        option.value = source.source;
                        option.textContent = source.source;
                        if (source.description) option.title = source.description;
                    }
                    sourceSelect.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Error fetching sources:', error);
        }
    }

    async function displayContents() {
        const value = sourceSelect.value;
        currentSource = value;
        documentModal.innerHTML = "";
        if (!value) {
            messageInput.disabled = true;
            sendBtn.disabled = true;
            chatContainer.innerHTML = `<div class="welcome-message"><i class="fas fa-robot">
                                        </i><p>Select a source and start chatting</p></div>`;
            return;
        }
        messageInput.disabled = false;
        sendBtn.disabled = false;
        //chatContainer.innerHTML = '';
        // Select All toggle
        
            // Show message only if source changed
        if (value !== lastSource) {
            showMessage('bot', `Now chatting with source: <strong>${value}</strong>`);
            lastSource = value;
            isFirstModalOpen = true;  // reset modal open flag for new source
        }

        
        const selectAllDiv = document.createElement('div');
        selectAllDiv.className = "flex items-center mb-2";
        const { label: selectAllLabel, input: selectAllInput } = createToggleSwitch(true);
        selectAllInput.id = "selectAll";
        const selectAllText = document.createElement('span');
        selectAllText.className = "ml-3 font-medium";
        selectAllText.style.backgroundColor = "transparent";
        selectAllText.textContent = "Select All";
        selectAllLabel.appendChild(selectAllText);
        selectAllDiv.appendChild(selectAllLabel);
        documentModal.appendChild(selectAllDiv);

        // Fetch documents
        let items = [];
        try {
            items = await fetchDocuments(value);
        } catch (error) {
            console.error("Error fetching documents:", error);
            return;
        }
        const toggles = [];
        const merged = {};
        
        items.forEach(({ filename, chunks, id }) => { 
            if (!merged[filename]) { 
                merged[filename] = { totalChunks: 0, docIDs: [] }; 
            }
            merged[filename].totalChunks += chunks; 
            merged[filename].docIDs.push(id);
        });
        
        // Convert back to array
        const grouped_items = Object.entries(merged).map(([filename, data]) => ({ 
           filename,
           totalChunks: data.totalChunks,
           docIDs: data.docIDs 
        }));
        console.log("grouped_items",grouped_items);

        window.sourceSelections = window.sourceSelections || {};
        // Initialize selection per source on first open
        if (!window.sourceSelections[value]) {
            window.sourceSelections[value] = new Set(grouped_items.map(item => item.filename));
        }
        
        // Update global reference
        window.selectedFilenames = window.sourceSelections[value];

        
        grouped_items.forEach((item, idx) => {
            const rowDiv = document.createElement('div');
            rowDiv.className = 'flex items-center justify-between border-b py-2 relative';
            const { label: toggleLabel, input: toggleInput } = createToggleSwitch(true);
            toggleInput.dataset.idx = idx;
            toggleInput.checked = selectedFilenames.has(item.filename);
//             selectedFilenames.add(item.filename);
            
            toggleInput.addEventListener('change', () => {
                if (toggleInput.checked) window.selectedFilenames.add(item.filename);
                else window.selectedFilenames.delete(item.filename);
                selectAllInput.checked = toggles.length > 0 && toggles.every(tg => tg.checked);
                window.sourceSelections[value] = new Set(window.selectedFilenames);
            });
            toggles.push(toggleInput);
            
            const contentDiv = document.createElement('div');
            contentDiv.className = "break-words max-w-[50%]";
            contentDiv.innerHTML = `<div class="font-bold text-[#111715]">${item.filename}</div><div class="text-sm text-[#648779]">Chunks: ${item.totalChunks}</div>`;
            const sourceDeleteButton = document.createElement('button');
            sourceDeleteButton.className = 'ml-3 p-1 rounded hover:bg-[#ffe5e5] cursor-pointer';
            sourceDeleteButton.title = 'Delete Source';
            sourceDeleteButton.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="#ef4444" class="w-5 h-5"><path stroke-linecap="round" stroke-linejoin="round" d="M6 7h12M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2m2 0v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V7h12z" /><path stroke-linecap="round" stroke-linejoin="round" d="M10 11v6m4-6v6" /></svg>`;
            sourceDeleteButton.addEventListener("click", () => {
                const deletefileName = item.filename
                console.log("File selected to delete : " + deletefileName);
                console.log("Document Id for deleting files ", item.docIDs);
                Swal.fire({
                    title: 'Are you sure?',
                    html: `Confirm to delete this Document <b>${item.filename}</b> from the source <b>${value}</b>?`,
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonText: 'Yes, delete it!',
                    cancelButtonText: 'Cancel'
                }).then(result => {
                    if (result.isConfirmed) deleteCall(item.docIDs, value, item.filename);
                });
            });
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'flex items-center gap-2';
            actionsDiv.appendChild(toggleLabel);
            actionsDiv.appendChild(sourceDeleteButton);
            rowDiv.appendChild(contentDiv);
            rowDiv.appendChild(actionsDiv);
            documentModal.appendChild(rowDiv);
        });
        // Set initial Select All state
        selectAllInput.checked = toggles.length > 0 && toggles.every(tg => tg.checked);

        selectAllInput.addEventListener('change', () => {
            const isChecked = selectAllInput.checked;
            toggles.forEach((toggleInput, idx) => {
                toggleInput.checked = isChecked;
                const filename = grouped_items[idx].filename;
                if (isChecked) window.selectedFilenames.add(filename);
                else window.selectedFilenames.delete(filename);
            });
             // Sync back to per-source selections
            window.sourceSelections[value] = new Set(window.selectedFilenames);    
        });
        console.log("Selected filenames:", [...window.selectedFilenames]);
        
    }
    

    async function handleSourceChange() {
        await displayContents();
    }
        
    viewFiles.addEventListener("click", async () => {
        const source = sourceSelect.value;
        if(!source) {
            Swal.fire({
                icon: 'info',
                title: "No Source Selected",
                text: "Please Select a source first, to view files."                
            });
            return;
        }
        
        currentSource = source;
        await displayContents();
        modal.classList.remove('hidden');
    })

    async function deleteCall(deleteId, source_name, deletefileName) {
        const formData = new FormData();
        formData.append('source_name', source_name);
        deleteId.forEach(Del_id => {
            formData.append('deleteId', Del_id);
        })
        try {
            const response = await fetch(getWebAppBackendUrl('/delete_document'), { method: 'DELETE', body: formData });
            if (response.ok) {
                Swal.fire({
                    title: 'Delete Info',
                    html: `Document <b>${deletefileName}</b> <br> Deleted Successfully from the source <br> <b>${source_name}</b>`,
                    icon: 'success',
                    confirmButtonText: 'OK'
                }).then(result => { if (result.isConfirmed) handleSourceChange(); });
            } else {
                Swal.fire({
                    title: 'Delete Info',
                    html: `Error Deleting the Document <b>${deletefileName}</b> from the source <b>${source_name}</b>`,
                    icon: 'error',
                    confirmButtonText: 'OK'
                });
            }
        } catch (error) {
            Swal.fire({
                title: 'Delete Info',
                html: `Error Deleting the Document <b>${deletefileName}</b> from the source <b>${source_name}</b>`,
                icon: 'error',
                confirmButtonText: 'OK'
            });
        }
    }

    async function clearSessionHistory() {
        console.log("Using clearSessionHistory");
        try {
            const response = await fetch(getWebAppBackendUrl('/clear_session'), {method: 'POST'});
            if (response.ok){
                Swal.fire({
                    title: 'Session Info',
                    html: `Current Session history was cleared.`,
                    icon: 'success',
                    confirmButtonText: "OK" 
                }).then(result => { if (result.isConfirmed) window.location.reload(); });
            }else {
                Swal.fire({
                    title: 'Session Info',
                    html: `Error Deleting the Current session`,
                    icon: 'error',
                    confirmButtonText: 'OK'
                });
            }
        } catch(error) {
            Swal.fire({
                title: 'Session Info',
                html: `Error Deleting the Current session`,
                icon: 'error',
                confirmButtonText: "OK"
            })
        }       
    }
     

    
    async function fetchDocuments(source) {
        if (!source) return [];
        try {
            const response = await fetch(getWebAppBackendUrl('/list_source_documents'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source })
            });
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            const data = await response.json();
            let documentsList = [];
            if (data.documents && Array.isArray(data.documents)) documentsList = data.documents;
            else if (Array.isArray(data)) documentsList = data;
            documents = documentsList;
            return documents;
        } catch (error) {
            console.error('Error fetching documents:', error);
            return [];
        }
    }

    function checkUploadButton() { 
        const hasFileInput = fileInput.files && fileInput.files.length > 0;
        const hasDroppedFile = droppedFiles  && droppedFiles.length >0;
        
        const shouldEnable = hasFileInput || hasDroppedFile;
        uploadBtn.disabled = !shouldEnable;
        
        if (shouldEnable) {
        uploadBtn.classList.add('upload-enabled');
        uploadBtn.classList.remove('upload-disabled'); } 
        else {
        uploadBtn.classList.add('upload-disabled');
        uploadBtn.classList.remove('upload-enabled');}
    }
    
    function checkUploadFolderButton() { 
        const hasFolderInput = folderInput.files.length > 0;
        
        const shouldEnable = hasFolderInput ;
        uploadFolder.disabled = !shouldEnable;
       
        if (shouldEnable) {
            uploadFolder.classList.add('upload-enabled');
            uploadFolder.classList.remove('upload-disabled');  }
        else {
            uploadFolder.classList.add('upload-disabled');
            uploadFolder.classList.remove('upload-enabled'); }
    
    }
    
//     function checkUploadButton() { uploadBtn.disabled = fileInput.files.length === 0; }
//     function checkUploadFolderButton() { uploadFolder.disabled = folderInput.files.length === 0; }

    async function handleDocumentUpload() {
        console.log("Calling Document Upload")
        const sourceName = sourceSelect.value;
        const file = fileInput.files[0] || (droppedFiles ? droppedFiles[0] : null);
        
        if (!sourceName || !file) return;
        uploadBtn.disabled = true;
        uploadProgress.classList.remove('hidden');
        progressBar.style.width = '0%';
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += 5;
            showLoadingText();
            if (progress > 90) { 
                clearInterval(progressInterval);
                showLoadingText(500, 5000);
               }
            progressBar.style.width = `${progress}%`;
        }, 300);
        const formData = new FormData();
        formData.append('file', file);
        formData.append('source_name', sourceName);
        try {
            const response = await fetch(getWebAppBackendUrl('/upload'), { method: 'POST', body: formData });
            clearInterval(progressInterval);
            progressBar.style.width = '100%';
            if (response.ok) {
                selectedFilesDiv.innerHTML = '';
                fileInput.value = '';
                droppedFiles = null;
                checkUploadButton();
                showMessage('bot', `Document <strong>${file.name}</strong> uploaded successfully to source <strong>${sourceName}</strong>`);
                Swal.fire({
                    title: 'Upload Info',
                    html: `Document <b>${file.name}</b> <br> Uploaded Successfully to the source <br> <b>${sourceName}</b>`,
                    icon: 'success',
                    confirmButtonText: 'OK'
                }).then(result => { if (result.isConfirmed) displayContents(); });
            } else {
                selectedFilesDiv.innerHTML = '';
                Swal.fire({
                    title: 'Upload Info',
                    html: `Failed to upload Document <b>${file.name}</b> <br> to the source <br> <b>${sourceName}</b>`,
                    icon: 'error',
                    confirmButtonText: 'OK'
                }).then(result => { if (result.isConfirmed) handleSourceChange(); });
            }
        } catch (error) {
            selectedFilesDiv.innerHTML = '';
            clearInterval(progressInterval);
            hideLoadingText();
            Swal.fire({
                title: 'Upload Info',
                html: `Failed to upload Document <b>${file.name}</b> <br> to the source <br> <b>${sourceName}</b>`,
                icon: 'error',
                confirmButtonText: 'OK'
            }).then(result => { if (result.isConfirmed) handleSourceChange(); });
        } finally {
            selectedFilesDiv.innerHTML = '';
            setTimeout(() => {
                uploadProgress.classList.add('hidden');
                progressBar.style.width = '0%';
                hideLoadingText();
                uploadBtn.disabled = false;
            }, 1000);
        }
    }

    async function handleFolderUpload() {
        const sourceName = sourceSelect.value;
        const files = folderInput.files 
        if (!sourceName || files.length === 0) return;
        uploadFolder.disabled = true;
        uploadProgress.classList.remove('hidden');
        progressBar.style.width = '0%';
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += 5;
             showLoadingText();
            if (progress > 90){ 
                clearInterval(progressInterval);
                showLoadingText(500, 5000);
                }
            progressBar.style.width = `${progress}%`;
        }, 300);
        try {
            for (const file of files) {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('source_name', sourceName);
                const response = await fetch(getWebAppBackendUrl('/upload'), { method: 'POST', body: formData });
                if (!response.ok) throw new Error(`Failed to upload file: ${file.name}`);
            }
            selectedFilesDiv.innerHTML = '';
            checkUploadFolderButton();
            clearInterval(progressInterval);
            progressBar.style.width = '100%';
            showMessage('bot', `Folder uploaded successfully to the source <strong>${sourceName}</strong>`);
            hideLoadingText();
            Swal.fire({
                title: 'Upload Info',
                html: `Folder Uploaded Successfully to the source <br> <b>${sourceName}</b>`,
                icon: 'success',
                confirmButtonText: 'OK'
            }).then(result => { if (result.isConfirmed) displayContents(); });
        } catch (error) {
            clearInterval(progressInterval);
            hideLoadingText();
            Swal.fire({
                title: 'Upload Info',
                html: `Failed to upload Folder <br> to the source <br> <b>${sourceName}</b>`,
                icon: 'error',
                confirmButtonText: 'OK'
            }).then(result => { if (result.isConfirmed) handleSourceChange(); });
        } finally {
            selectedFilesDiv.innerHTML = '';
            setTimeout(() => {
                uploadProgress.classList.add('hidden');
                progressBar.style.width = '0%';
                hideLoadingText();
                uploadFolder.disabled = false;
            }, 1000);
            folderInput.value = '';
            checkUploadFolderButton();
        }
    }

    function displaySelectedFiles(files, isFolder = false) {
        if (!files || files.length === 0) {
            selectedFilesDiv.innerHTML = '';
            return;
        }
        let html_content = '';
        if (isFolder && files[0].webkitRelativePath) {
            const folderName = files[0].webkitRelativePath.split('/')[0];
            html_content += `<div class="font-bold">Folder: ${folderName}</div>`;
        }
        for (let i = 0; i < files.length; i++) {
            let fileName = files[i].name;
            let folderName = '';
            if (isFolder && files[i].webkitRelativePath) {
                const parts = files[i].webkitRelativePath.split('/');
                if (parts.length > 1) folderName = parts.slice(0, -1).join('/');
            }
            html_content += `<div>${fileName}${folderName ? ` <span class="text-[#648779]">(${folderName})</span>` : ''}</div>`;
        }
        selectedFilesDiv.innerHTML = html_content;
    }

    async function sendMessage(message) {
        if (!message.trim() || !currentSource) return;
        showMessage('user', message);
        //showTypingIndicator();
        messageInput.disabled = true;
        sendBtn.disabled = true;
        console.log("selectedFilenames inside sendMEsaage ",window.selectedFilenames )
        const selectedFileList = Array.from(window.selectedFilenames);
        try {
            const formData = new FormData();
            formData.append('question', message);
            formData.append('source_name', currentSource);
            formData.append('selectedFileList', selectedFileList);
            console.log("selectedFileList ", selectedFileList);
            showLoader();
//             toggleBouncingLoader(true);
            const response = await fetch(getWebAppBackendUrl('/api/chat'), { method: 'POST', body: formData });
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            const result = await response.json();
            //removeTypingIndicator();
            if (result.status === "success") {
                removeLoader();
//                 toggleBouncingLoader(false);
                
                if (result.rephrased_questions && result.rephrased_questions.length > 0) {
//                     const questionsMarkdown = "**Search queries:**\n" + result.rephrased_questions.map(q => `- ${q}`).join('\n');
//                     showMessage('bot', questionsMarkdown, null, true);
                }
                setTimeout(() => showMessage('bot', result.answer), 500);
            } else {
                showMessage('bot', `Error: ${result.error || 'Failed to process message'}`);
            }
        } catch (error) {
            //removeTypingIndicator();
//             toggleBouncingLoader(false);
               removeLoader();
            showMessage('bot', 'Error processing your message. Please try again.');
        } finally {
            messageInput.disabled = false;
            sendBtn.disabled = false;
            messageInput.focus();
        }
    }

    function showMessage(type, content, metadata = null, isSystem = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${type}-message px-4 py-2 rounded-xl  whitespace-pre-line inline-block max-w-[75%]`;
        if (isSystem) messageDiv.classList.add('system-message');
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        if (type === 'bot' || isSystem) {
            if (typeof marked !== 'undefined') messageContent.innerHTML = marked.parse(content);
            else messageContent.innerHTML = content;
            if (metadata) {
                const sourceInfo = document.createElement('div');
                sourceInfo.className = 'source-info';
                sourceInfo.textContent = `Source: ${metadata}`;
                messageContent.appendChild(sourceInfo);
            }
        } else {
            messageContent.textContent = content;
        }
        messageDiv.appendChild(messageContent);
        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function showTypingIndicator() {
        const indicatorDiv = document.createElement('div');
        indicatorDiv.className = 'chat-message bot-message typing-indicator';
        indicatorDiv.id = 'typingIndicator';
        const indicatorContent = document.createElement('div');
        indicatorContent.className = 'message-content';
        for (let i = 0; i < 3; i++) {
            const dot = document.createElement('div');
            dot.className = 'typing-dot';
            indicatorContent.appendChild(dot);
        }
        indicatorDiv.appendChild(indicatorContent);
        chatContainer.appendChild(indicatorDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) indicator.remove();
    }
    
    // JavaScript function to show the bouncing loader inside a container   
    function showLoader() {
      const loaderBubble = document.createElement('div');
      loaderBubble.id = 'loaderBubble';
      loaderBubble.className = 'self-start bg-white p-3 rounded-xl shadow-sm max-w-[80%]';
      loaderBubble.innerHTML = `
        <div class="bouncing-loader">
          <div></div>
          <div></div>
          <div></div>
        </div>
      `;

      chatContainer.appendChild(loaderBubble);
      chatContainer.scrollTop = chatContainer.scrollHeight; // Auto-scroll
    }
    
    // JavaScript function to show the bouncing loader inside a container   
    function removeLoader() {
      const loaderBubble = document.getElementById('loaderBubble');
      if (loaderBubble) loaderBubble.remove();
    }

    function showLoadingText(fadeDuration = 500, messageInterval = 5000) {
      if (isLoadingTextActive) return; //  Already active, don't re-trigger
      isLoadingTextActive = true;

      const loadingText = document.getElementById("loadingText");
      loadingText.classList.remove("hidden");
      loadingText.textContent = loadingMessages[0];
      loadingIndex = 1;

      loadingInterval = setInterval(() => {
        loadingText.classList.add("fade-out");
        setTimeout(() => {
          loadingText.textContent = loadingMessages[loadingIndex];
          loadingIndex = (loadingIndex + 1) % loadingMessages.length;
          loadingText.classList.remove("fade-out");
        }, fadeDuration);
      }, messageInterval);
    }

    function hideLoadingText() {
      clearInterval(loadingInterval);
      const loadingText = document.getElementById("loadingText");
      loadingText.classList.add("hidden");
      isLoadingTextActive = false; // Reset flag
}

    
    function createToggleSwitch(initialChecked = true) {
        const label = document.createElement('label');
        label.className = "relative inline-flex items-center cursor-pointer";
        const input = document.createElement('input');
        input.type = "checkbox";
        input.className = "sr-only peer";
        input.checked = initialChecked;
        const span = document.createElement('span');
        span.className = "w-11 h-6 bg-gray-200 rounded-full peer peer-checked:bg-[#1db77c] transition-colors duration-200";
        const dot = document.createElement('span');
        dot.className = "absolute left-1 top-1 w-4 h-4 bg-white rounded-full transition-transform duration-200 peer-checked:translate-x-5";
        span.appendChild(dot);
        label.appendChild(input);
        label.appendChild(span);
        return { label, input };
    }
});
