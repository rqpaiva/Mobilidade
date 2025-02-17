export interface ISelected {
  name: string | number;
  value: string | number;
}

export type TFilterFieldType =
  | 'select'
  | 'text'
  | 'toggle'

export interface IFilterFormField {
  id: string;
  type: TFilterFieldType;
  label: string;
  placeholder?: string;
  minDate?: Date;
  maxDate?: Date;
  options?: any;
  mask?: string;
  optionsMask?: string;
  selected?: undefined | ISelected;
  state?: Date | string | number | boolean | null;
  amountState?: Date | string | number | boolean | null;
  maxLength?: number;
  setState?: React.Dispatch<React.SetStateAction<any | null>>;
  amountSetState?: React.Dispatch<React.SetStateAction<any | null>>;
  callback?: () => void;
  size?: number;
}
