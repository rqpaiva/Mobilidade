document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('uploadForm');
    
    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        
        const fileInput = document.getElementById('fileInput');
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);

        try {
            const response = await fetch('/upload_csv', {
                method: 'POST',
                body: formData,
            });

            if (response.ok) {
                const result = await response.json();
                alert(result.success || 'Arquivo enviado com sucesso!');
            } else {
                const error = await response.json();
                alert(error.error || 'Erro ao enviar arquivo.');
            }
        } catch (err) {
            console.error(err);
            alert('Erro ao conectar ao servidor.');
        }
    });
});