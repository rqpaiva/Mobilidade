import React from 'react';
import {ISelected} from './FilterField';

import '../../styles/filterField.css'

interface FilterSelectProps {
	id: string
	label: string;
	options: { name: string; value: string }[];
	value: ISelected | undefined;
	onChange: (value: string) => void;
}

const FilterSelect: React.FC<FilterSelectProps> = ({ id, label, options, value, onChange }) => {
	return (
		<div className='filter-container'>
			<label className='filter-label'>{label}</label>
			<select
				value={ value?.value }
				// onChange={(e) => onChange(e.target.value)}
				className='filter-input'
			>
				<option></option>
				{options.map((opt) => (
					<option key={opt.value} value={opt.value}>
						{opt.name}
					</option>
				))}
			</select>
		</div>
	);
};

export default FilterSelect;
