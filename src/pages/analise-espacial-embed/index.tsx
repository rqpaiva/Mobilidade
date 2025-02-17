import React, {useState} from 'react';
import Navbar from '../../components/navbar';
import {FormProvider, useForm} from 'react-hook-form';

import '../../styles/subpage.css'
import MongoEmbed from '../../components/mongoEmbed';
import {analiseEspacialFilters} from './filterUtil';
import FilterInput from '../../components/filter/FilterInput';
import FilterSelect from '../../components/filter/FilterSelect';
import FilterForm from '../../components/filter/FilterForm';

interface AnaliseEspacialForm {
  createdAt: Date | null;
  status: string | null;
  distanciaMotorista: number | null;
  distanciaRota: number | null;
  bairroCliente: string | null;
}

const AnaliseEspacialEmbed = () => {
  const [filters, setFilters] = useState<Record<string, any>>()
  const filterMethods = useForm<AnaliseEspacialForm>({
    defaultValues: {
      createdAt: null,
      status: '',
      distanciaMotorista: null,
      distanciaRota: null,
      bairroCliente: '',
    },
  });

  const submitFilters = () => {
    const createdAt = filterMethods.watch('createdAt')
    const status = filterMethods.watch('status')
    const driverDistance = filterMethods.watch('distanciaMotorista')
    const routeDistance = filterMethods.watch('distanciaRota')
    const suburbClient = filterMethods.watch('bairroCliente')
    const filters: Record<string, any> = {};


    if (createdAt) filters['created_at'] = { '$eq': createdAt };
    if (status) filters['status'] = { '$eq': status };
    if (driverDistance) filters['driver_distance'] = { '$gte': driverDistance };
    if (routeDistance) filters['route_distance'] = { '$gte': routeDistance };
    if (suburbClient) filters['suburb_client'] = { '$eq': suburbClient };
    setFilters(filters)
  };

  return (
    <div className='v1_17'>
      <span className='v5_3'>Análise Espacial (Embed)</span>
      <div className='container-content'>
        <Navbar/>
        <FormProvider {...filterMethods}>

          <FilterForm onSubmit={filterMethods.handleSubmit(submitFilters)} size={3}>
            {analiseEspacialFilters.map((field) => {
              switch (field.type) {
                case 'text':
                  return (
                    <FilterInput
                      id = { field.id }
                      placeholder = {field.placeholder || ''}
                      label = {field.label}
                      type = {field.type}
                      value={ String(field.state ?? '') }
                    />
                  );
                case 'select':
                  return (
                    <FilterSelect
                      id = { field.id }
                      label={field.label}
                      options={field.options}
                      value={field.selected}
                      onChange={field.setState!}
                    />
                  );
                default:
                  return <div id={field.id} />;
              }
            })}
          </FilterForm>
        </FormProvider>
      </div>
      <MongoEmbed filters={filters}/>
    </div>
  );
};

export default AnaliseEspacialEmbed;
