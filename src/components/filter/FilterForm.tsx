import React, { Children, ReactNode } from 'react';
import styled from 'styled-components';

import '../../styles/filterField.css'

const FiltersContainer = styled.div`
	background-color: #1b1b1b;
	margin-bottom: 10px;
	padding: 20px;
  flex-grow: 1;
  justify-content: center;
`;

interface IFiltersForm {
  children: ReactNode;
  onSubmit: () => void;
  title?: boolean;
  size?: number;
}

const InputFieldsContainer = styled.div<{ fieldQuantity: number }>`
	display: grid;
  grid-template-columns: repeat(${(props) => props.fieldQuantity}, 1fr);
	grid-column-gap: 20px;
`;

const ButtonsContainer = styled.div`
	display: flex;
	justify-content: flex-end;
	width: 100%;
	&& {
		button {
			width: 200px;

			&:nth-of-type(2) {
				margin-left: 10px;
			}
		}
	}
`;


const FilterForm: React.FC<IFiltersForm> = ({ children, onSubmit, size}) => {
  const FieldQuantity = size || Children.count(children);


  return (
    <FiltersContainer>
      <InputFieldsContainer fieldQuantity={FieldQuantity} id='fields'>
        {children}
      </InputFieldsContainer>
      <ButtonsContainer>
        <button className='filter-button' onClick={onSubmit}> Submit </button>
      </ButtonsContainer>
    </FiltersContainer>
  );
};

export default FilterForm;
