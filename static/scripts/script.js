document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('fileInput');
    const fileLabel = document.querySelector('.custom-file-label');
    const textUpload = document.querySelector('.text-upload');
    const buttonSubimit = document.querySelector('.buttonSubimit');
    const uploadForm = document.getElementById('uploadForm');

    // Atualizar o texto do botão ao selecionar um arquivo
    fileInput.addEventListener('change', function() {
        if (fileInput.files.length > 0) {
            textUpload.textContent = fileInput.files[0].name;
            fileLabel.classList.add('hidenButton');
            buttonSubimit.classList.remove('hidenButton');
        } else {
            textUpload.textContent = 'Nenhum arquivo selecionado';
        }
    });

    // Gerenciar o envio do formulário
    uploadForm.addEventListener('submit', async function(event) {
        event.preventDefault();

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();

            if (response.ok) {
                alert(result.success || 'Arquivo carregado com sucesso!');
                location.reload(); // Recarrega a página para atualizar a tabela
            } else {
                alert(result.error || 'Ocorreu um erro ao carregar o arquivo.');
            }
        } catch (error) {
            console.error('Erro no envio:', error);
            alert('Erro ao conectar ao servidor.');
        }
    });
});