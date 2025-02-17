import {IFilterFormField} from '../../components/filter/FilterField';

const statusOptions = [
  {name: 'Cancelada pelo Passageiro', value: 'Cancelada pelo Passageiro'},
  {name: 'Cancelada pelo Taxista', value: 'Cancelada pelo Taxista'},
  {name: 'Finalizada', value: 'Finalizada'},
]

const bairroOptions = [
  {name: 'Todos', value: ''},
  {name: 'Copacabana', value: 'Copacabana'},
  {name: 'Tijuca', value: 'Tijuca'},
  {name: 'Centro', value: 'Centro'},
  {name: 'Botafogo', value: 'Botafogo'},
]

export const analiseEspacialFilters: IFilterFormField[] = [
  {
    id: 'createdAt',
    type: 'text',
    label: 'Created At',
    placeholder: '2025-01-01',
  },
  {
    id: 'status',
    type: 'select',
    label: 'Status',
    options: statusOptions
  },
  {
    id: 'distanciaMotorista',
    type: 'text',
    label: 'Distância do Motorista (metros)',
    placeholder: '1000',
  },
  {
    id: 'distanciaRota',
    type: 'text',
    label: 'Distância da Rota (metros)',
    placeholder: '5000',
  },
  {
    id: 'bairroCliente',
    type: 'select',
    label: 'Bairro do Cliente',
    options: bairroOptions
  },
]

export const formatDateFilter = (date: Date) => {
  const startOfDay = new Date(date);
  startOfDay.setUTCHours(0, 0, 0, 0);

  const endOfDay = new Date(date);
  endOfDay.setUTCDate(endOfDay.getUTCDate() + 1);
  endOfDay.setUTCHours(0, 0, 0, 0);

  return {
    $gte: startOfDay,
    $lt: endOfDay,
  }
}