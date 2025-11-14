import os
from pymongo import MongoClient
from dotenv import load_dotenv
import pandas as pd


def upload_excel_to_mongodb():
    # Load environment variables
    load_dotenv()

    # MongoDB connection
    try:
        client = MongoClient(os.getenv("MONGO_URI"))
        db = client["mobility_data"]
        collection = db["reclame_aqui_complaints"]

        # Possible file paths
        file_paths = [
            os.path.join(os.getcwd(), 'data', 'reclame_aqui_comentarios.xlsx'),
            '/home/raquel/mobilidade/data/reclame_aqui_comentarios.xlsx'
        ]

        # Find the existing file
        file_path = None
        for path in file_paths:
            if os.path.exists(path):
                file_path = path
                break

        if not file_path:
            raise FileNotFoundError("Excel file not found in any of the specified paths")

        # Read Excel file
        df = pd.read_excel(file_path, sheet_name='Comentarios')

        # Clean column names (remove spaces and special characters)
        df.columns = [col.strip().replace(' ', '_').lower() for col in df.columns]

        # Convert dataframe to dictionary records
        records = df.to_dict('records')

        # Insert into MongoDB
        if records:
            result = collection.insert_many(records)
            print(f"Successfully inserted {len(result.inserted_ids)} documents")
        else:
            print("No records to insert")

    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    upload_excel_to_mongodb()