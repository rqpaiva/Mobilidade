import React from 'react';
import {useIframeGraphApi} from '../hooks/UseBackendApi';
import {Mosaic} from 'react-loading-indicators';

interface IFrameLoader {
  endpoint: string;
}

const FrameLoader: React.FC<IFrameLoader> = ({ endpoint }) => {
  const { graphData, isLoadingGraphs } = useIframeGraphApi(endpoint);

  return (
    isLoadingGraphs ? <Mosaic color='#00bfa6' size='medium' text='' textColor=''/> :
      <div className='iframe-container' dangerouslySetInnerHTML={{__html: graphData}}/>
  );
};

export default FrameLoader;