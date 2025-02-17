import {IFilterFormField} from '../../components/filter/FilterField';

const statusOptions = [
  {name: 'Cancelada pelo Passageiro', value: 'CANCELADA_PELO_PASSAGEIRO'},
  {name: 'Cancelada pelo Taxista', value: 'CANCELADA_PELO_TAXISTA'},
  {name: 'Finalizada', value: 'FINALIZADA'},
]

const bairroOptions = [
  {name: 'Todos', value: ''},
  {name: 'Copacabana', value: 'COPACABANA'},
  {name: 'Tijuca', value: 'TIJUCA'},
  {name: 'Centro', value: 'CENTRO'},
  {name: 'Botafogo', value: 'BOTAFOGO'},
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