import pandas as pd
import numpy as np
import random

np.random.seed(42)
random.seed(42)

data = []
root_causes = ['Contamination', 'Equipment Malfunction', 'Operator Error', 'Material Issue', 'Parameter Deviation']
defect_types = ['Particle', 'Void', 'Bridge', 'Scratch', 'Misalignment', 'Discoloration']

for i in range(1, 101):
    sample_id = f'S{i:03d}'
    lot_id = f'Lot{random.randint(1, 20):02d}'
    is_defective = random.random() < 0.3

    # Baseline good parameters
    temperature = np.random.normal(350, 10)
    pressure = np.random.normal(1.0, 0.05)
    deposition_time = np.random.normal(60, 5)
    etch_rate = np.random.normal(5.0, 0.5)
    particle_count = max(0, np.random.poisson(3))
    line_width_variation = np.random.normal(0, 0.05)
    defect_type = 'None'
    root_cause = 'None'

    if is_defective:
        cause = random.choice(root_causes)
        root_cause = cause

        if cause == 'Contamination':
            particle_count += np.random.poisson(15)
            defect_type = random.choice(['Particle', 'Discoloration'])
        elif cause == 'Equipment Malfunction':
            etch_rate += np.random.normal(2, 0.5)  # uneven etch
            defect_type = 'Void'
        elif cause == 'Operator Error':
            deposition_time += np.random.normal(20, 5)
            defect_type = 'Bridge'
        elif cause == 'Material Issue':
            line_width_variation += np.random.normal(0.3, 0.1)
            defect_type = 'Misalignment'
        elif cause == 'Parameter Deviation':
            dev = random.choice(['temp', 'pressure', 'time'])
            if dev == 'temp':
                temperature += np.random.normal(40, 10) * random.choice([-1, 1])
            elif dev == 'pressure':
                pressure += np.random.normal(0.5, 0.1) * random.choice([-1, 1])
            else:
                deposition_time += np.random.normal(15, 5) * random.choice([-1, 1])
            defect_type = random.choice(defect_types)

    row = {
        'Sample_ID': sample_id,
        'Lot_ID': lot_id,
        'Temperature': round(temperature, 2),
        'Pressure': round(pressure, 2),
        'Deposition_Time': round(deposition_time, 2),
        'Etch_Rate': round(etch_rate, 2),
        'Particle_Count': int(particle_count),
        'Line_Width_Variation': round(line_width_variation, 4),
        'Defect_Type': defect_type,
        'Root_Cause': root_cause,
        'Is_Defective': 'Yes' if is_defective else 'No'
    }
    data.append(row)

df = pd.DataFrame(data)
df.to_csv('chip_manufacturing_rca_dataset.csv', index=False)
print("Full 100-row dataset saved to 'chip_manufacturing_rca_dataset.csv'")
print("\nFirst 10 rows:\n", df.head(10))