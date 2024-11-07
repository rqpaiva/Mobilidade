document.addEventListener('DOMContentLoaded', function () {
    // Função genérica para uploads
    async function handleUpload(event, formId, actionUrl, successMessage) {
        event.preventDefault();
        const form = document.getElementById(formId);
        const formData = new FormData(form);

        try {
            const response = await fetch(actionUrl, {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();
            if (response.ok) {
                alert(successMessage);
                location.reload(); // Recarregar para ver atualizações
            } else {
                alert(result.error || 'Erro no upload do arquivo.');
            }
        } catch (error) {
            console.error(`Erro ao enviar ${formId}:`, error);
            alert('Erro ao conectar ao servidor.');
        }
    }

    // Gerenciar uploads
    document.getElementById('uploadCSVForm').addEventListener('submit', (event) =>
        handleUpload(event, 'uploadCSVForm', '/upload', 'CSV carregado com sucesso!')
    );

    document.getElementById('uploadFavelasForm').addEventListener('submit', (event) =>
        handleUpload(event, 'uploadFavelasForm', '/upload_favelas', 'GeoJSON de Favelas atualizado com sucesso!')
    );

    document.getElementById('uploadCensoForm').addEventListener('submit', (event) =>
        handleUpload(event, 'uploadCensoForm', '/upload_censo', 'GeoJSON do Censo atualizado com sucesso!')
    );
});