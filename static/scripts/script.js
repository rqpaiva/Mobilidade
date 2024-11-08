document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('uploadForm');

    form.addEventListener('submit', async function (event) {
        event.preventDefault(); // Evita o reload da página

        const fileInput = document.getElementById('fileInput');
        const file = fileInput.files[0]; // Pega o arquivo selecionado

        if (!file) {
            alert('Por favor, selecione um arquivo para fazer o upload.');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/upload_csv', {
                method: 'POST',
                body: formData,
            });

            if (response.ok) {
                const result = await response.json();
                document.getElementById('message').textContent = result.success || 'Upload realizado com sucesso!';
            } else {
                const error = await response.json();
                document.getElementById('message').textContent = error.error || 'Erro no upload.';
            }
        } catch (err) {
            console.error(err);
            document.getElementById('message').textContent = 'Erro ao conectar ao servidor.';
        }
    });
});