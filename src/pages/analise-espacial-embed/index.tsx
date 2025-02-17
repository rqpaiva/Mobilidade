import React, {useMemo, useState} from 'react';
import Navbar from '../../components/navbar';
import {FormProvider, useForm} from 'react-hook-form';

import '../../styles/subpage.css'
import MongoEmbed from '../../components/mongoEmbed';
import {analiseEspacialFilters, formatDateFilter} from './filterUtil';
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
  const [filters, setFilters] = useState<Record<string, any> | null>(null);
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
    const newFilters: Record<string, any> = {};

    if (createdAt) newFilters['created_at'] = formatDateFilter(createdAt);
    if (status) newFilters['status'] = {'$eq': status};
    if (driverDistance) newFilters['driver_distance'] = {'$gte': Number(driverDistance)};
    if (routeDistance) { newFilters['route_distance'] = {'$gte': Number(routeDistance)}; filterMethods.unregister('distanciaRota') }
    if (suburbClient) newFilters['suburb_client'] = {'$eq': suburbClient};

    if (JSON.stringify(filters) !== JSON.stringify(newFilters)) {
      console.log(newFilters)
      setFilters(newFilters);
    }
  };

  const mongoEmbed = useMemo(() => <MongoEmbed filters={filters} />, [filters]);

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
                      id={field.id}
                      key={field.id}
                      placeholder={field.placeholder || ''}
                      label={field.label}
                      type={field.type}
                      value={String(field.state ?? '')}
                    />
                  );
                case 'select':
                  return (
                    <FilterSelect
                      id={field.id}
                      key={field.id}
                      label={field.label}
                      options={field.options}
                      value={field.selected}
                      onChange={(value) => filterMethods.setValue(field.id as keyof AnaliseEspacialForm, value)}
                    />
                  );
                default:
                  return <div key={field.id} id={field.id}/>;
              }
            })}
          </FilterForm>
        </FormProvider>
      </div>
      { mongoEmbed }
    </div>
  );
};

export default AnaliseEspacialEmbed;
