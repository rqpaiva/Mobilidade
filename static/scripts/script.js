document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('fileInput');
    const fileLabel = document.querySelector('.custom-file-label');
    const textUpload = document.querySelector('.text-upload');
    const buttonSubimit = document.querySelector('.buttonSubimit');

    
    fileInput.addEventListener('change', function() {
        if (fileInput.files.length > 0) {
            textUpload.textContent = fileInput.files[0].name;
            fileLabel.classList.add('hidenButton');
            buttonSubimit.classList.remove('hidenButton')

        } else {
            fileLabel.textContent = 'Nenhum arquivo selecionado';
        }
    });
});