import React from 'react';
import '../../styles/filterField.css'
import {useFormContext} from 'react-hook-form';

interface FilterInputProps {
	id: string,
	label: string;
	type: 'text' | 'number';
	value: string | number;
	placeholder: string;
}

const FilterInput: React.FC<FilterInputProps> = ({ id, label, type, placeholder }) => {
	const { register, setValue } = useFormContext();

	return (
		<div className='filter-container'>
			<label className='filter-label'>{label}</label>
			<input
				{...register(id)}
				type={type}
				placeholder={placeholder}
				onChange={(e) => setValue(id, e.target.value)}
				className='filter-input'
			/>
		</div>
	);
};

export default FilterInput;
