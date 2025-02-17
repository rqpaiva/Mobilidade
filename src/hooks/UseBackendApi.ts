import { baseURL } from './Config';
import useSWR from 'swr';
import axios from 'axios';

export const getHttpClient = () => {
  console.log(baseURL)
  return axios.create({
    baseURL,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      Authorization: localStorage.getItem('accessToken'),
    },
  });
}

export const useIframeGraphApi = (endpoint: string) => {
  const {
    data: graphData = '',
    error: graphErrors,
    mutate: mutateGraph,
  } = useSWR(endpoint, async (url) => {
    const response = await getHttpClient().get<any>(url);
    const parser = new DOMParser();
    const doc = parser.parseFromString(response.data, 'text/html');
    return doc.querySelector('iframe')?.outerHTML;
  });

  const isLoadingGraphs = !graphErrors && !graphData;
  return {
    graphData,
    isLoadingGraphs,
    graphErrors,
    mutateGraph,
  } as const;
}