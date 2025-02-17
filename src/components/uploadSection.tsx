import React from 'react';

const UploadSection = () => {
  return (
    <div className='v15_21'>
      <div className='container-upload'>
        <form id='uploadForm' action='/upload_csv' method='POST' encType='multipart/form-data'>
          <div className='icon-upload'>⬆</div>
          <label htmlFor='fileInput' className='custom-file-label'>Selecionar Arquivo</label>
          <input type='file' id='fileInput' name='file' />
          <button type='submit' className='buttonSubmit hiddenButton'>Upload</button>
        </form>
      </div>
    </div>
  );
};

export default UploadSection;