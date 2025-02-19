import React from 'react';
import '../../styles/filterField.css'
import {useFormContext} from 'react-hook-form';

interface FilterInputProps {
	id: string,
	label: string;
	type: 'text' | 'number';
	value: string | number;
	placeholder: string;
	regex: RegExp | undefined
}

const FilterInput: React.FC<FilterInputProps> = ({ id, label, type, placeholder, regex }) => {
	const { register } = useFormContext();

	return (
		<div className='filter-container'>
			<label className='filter-label'>{label}</label>
			<input
				{...register(id)}
				pattern={regex?.source}
				type={type}
				placeholder={placeholder}
				className='filter-input'
			/>
		</div>
	);
};

export default FilterInput;
