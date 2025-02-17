import Chart from './chart';

import '../styles/dashboard.css'

interface MongoEmbedProps {
  filters?: Record<string, any> | null
}

const MongoEmbed = (props: MongoEmbedProps) => {
  return <div className='App'>
    <div className='charts'>
      <Chart height={'600px'} width={'800px'} filter={props.filters ?? {}} chartId={'d725cd12-caa3-44be-a974-824ea60c5ce7'}/>
      <Chart height={'600px'} width={'800px'} filter={props.filters ?? {}} chartId={'45c15229-d420-4f97-bf05-b36adda4eb8c'}/>
      <Chart height={'600px'} width={'800px'} filter={props.filters ?? {}} chartId={'ea3ce4e0-fe9c-4761-9f27-63aae29857c2'}/>
      <Chart height={'600px'} width={'800px'} filter={props.filters ?? {}} chartId={'03934f33-693c-4634-b694-3b6ef45a41ec'}/>
      <Chart height={'600px'} width={'800px'} filter={props.filters ?? {}} chartId={'b6943605-c9bc-480b-95d3-97c6fffe3253'}/>
      <Chart height={'600px'} width={'800px'} filter={props.filters ?? {}} chartId={'306c587e-afd0-4fac-ba67-077625318a85'}/>
    </div>
  </div>
};

export default MongoEmbed;
