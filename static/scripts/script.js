document.addEventListener('DOMContentLoaded', function() {
    // Referências para os elementos de upload
    const csvFileInput = document.getElementById('csvFileInput');
    const uploadCsvForm = document.getElementById('uploadCsvForm');

    const uploadFavelasForm = document.getElementById('uploadFavelasForm');
    const uploadCensoForm = document.getElementById('uploadCensoForm');

    // Atualizar o texto do botão de envio de CSV ao selecionar um arquivo
    csvFileInput.addEventListener('change', function() {
        if (csvFileInput.files.length > 0) {
            alert(`Arquivo selecionado: ${csvFileInput.files[0].name}`);
        } else {
            alert('Nenhum arquivo selecionado.');
        }
    });

    // Gerenciar o envio do formulário de upload de CSV
    uploadCsvForm.addEventListener('submit', async function(event) {
        event.preventDefault();

        if (csvFileInput.files.length === 0) {
            alert('Por favor, selecione um arquivo CSV.');
            return;
        }

        const formData = new FormData();
        formData.append('file', csvFileInput.files[0]);

        try {
            const response = await fetch('/upload_csv', {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();

            if (response.ok) {
                alert(result.success || 'Arquivo CSV carregado com sucesso!');
                location.reload(); // Recarrega a página para atualizar os dados
            } else {
                alert(result.error || 'Erro ao carregar o arquivo CSV.');
            }
        } catch (error) {
            console.error('Erro no envio do CSV:', error);
            alert('Erro ao conectar ao servidor para upload do CSV.');
        }
    });

    // Gerenciar o envio do formulário de upload do GeoJSON de Favelas
    uploadFavelasForm.addEventListener('submit', async function(event) {
        event.preventDefault();

        try {
            const response = await fetch('/upload_favelas', {
                method: 'POST',
            });

            const result = await response.json();

            if (response.ok) {
                alert(result.success || 'GeoJSON de Favelas carregado com sucesso!');
                location.reload(); // Recarrega a página para atualizar os dados
            } else {
                alert(result.error || 'Erro ao carregar o GeoJSON de Favelas.');
            }
        } catch (error) {
            console.error('Erro no envio do GeoJSON de Favelas:', error);
            alert('Erro ao conectar ao servidor para upload do GeoJSON de Favelas.');
        }
    });

    // Gerenciar o envio do formulário de upload do GeoJSON do Censo
    uploadCensoForm.addEventListener('submit', async function(event) {
        event.preventDefault();

        try {
            const response = await fetch('/upload_censo', {
                method: 'POST',
            });

            const result = await response.json();

            if (response.ok) {
                alert(result.success || 'GeoJSON do Censo carregado com sucesso!');
                location.reload(); // Recarrega a página para atualizar os dados
            } else {
                alert(result.error || 'Erro ao carregar o GeoJSON do Censo.');
            }
        } catch (error) {
            console.error('Erro no envio do GeoJSON do Censo:', error);
            alert('Erro ao conectar ao servidor para upload do GeoJSON do Censo.');
        }
    });
});