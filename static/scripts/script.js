document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('fileInput');
    const fileLabel = document.querySelector('.custom-file-label');
    const textUpload = document.querySelector('.text-upload');
    const buttonSubimit = document.querySelector('.buttonSubimit');
    const uploadForm = document.getElementById('uploadForm');
    const messageContainer = document.getElementById('message');

    // Atualiza o texto e exibe o botão "Analisar" ao selecionar o arquivo
    fileInput.addEventListener('change', function() {
        if (fileInput.files.length > 0) {
            textUpload.textContent = fileInput.files[0].name;
            fileLabel.classList.add('hidenButton');
            buttonSubimit.classList.remove('hidenButton');
        } else {
            textUpload.textContent = 'Nenhum arquivo selecionado';
            fileLabel.classList.remove('hidenButton');
            buttonSubimit.classList.add('hidenButton');
        }
    });

    // Envia o arquivo para o servidor ao clicar no botão "Analisar"
    uploadForm.addEventListener('submit', async function(event) {
        event.preventDefault(); // Impede o comportamento padrão do formulário

        if (fileInput.files.length === 0) {
            alert('Por favor, selecione um arquivo para continuar.');
            return;
        }

        const file = fileInput.files[0];
        const formData = new FormData();
        formData.append('file', file);

        try {
            // Faz a requisição para o endpoint de upload
            const response = await fetch('/upload_csv', {
                method: 'POST',
                body: formData,
            });

            // Verifica a resposta do servidor
            if (response.ok) {
                const result = await response.json();
                textUpload.textContent = result.success || 'Upload realizado com sucesso!';
            } else {
                const error = await response.json();
                textUpload.textContent = error.error || 'Erro no upload.';
            }
        } catch (err) {
            console.error('Erro ao enviar o arquivo:', err);
            textUpload.textContent = 'Erro ao conectar ao servidor.';
        } finally {
            buttonSubimit.classList.add('hidenButton'); // Oculta o botão após o envio
            fileLabel.classList.remove('hidenButton'); // Exibe novamente o botão de seleção
        }
    });
});