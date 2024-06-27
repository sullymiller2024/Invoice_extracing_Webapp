from flask import Flask, request, send_file , after_this_request
from werkzeug.utils import secure_filename
import openai
import pandas as pd
import pytesseract
import json
from openai import OpenAI
import os
import io
import fitz
from PIL import Image
app = Flask(__name__)
pytesseract.pytesseract.tesseract_cmd = '/app/.apt/usr/bin/tesseract'
tessdata_prefix = os.getenv('TESSDATA_PREFIX', '/default/path/if/variable/is/missing')
apiKey = os.getenv('OPENAI_API_KEY')
@app.route('/', methods=['POST'])
def upload_files():
  uploaded_files = request.files.getlist('invoices')
  if not uploaded_files:
        return 'No files uploaded', 400
  pdf_paths = []
  for file in uploaded_files:
    if file.filename != '':

      filename = secure_filename(file.filename)
      temp_path = os.path.join('/tmp', filename)
      file.save(temp_path)
      pdf_paths.append(temp_path)

  if not pdf_paths:
    return 'No valid files provided', 400


  result_file_path = process_invoices(pdf_paths)

  @after_this_request
  def remove_files(response):
    for path in pdf_paths:
      os.remove(path)
    os.remove(result_file_path)
    return response


  return send_file(result_file_path, as_attachment=True, download_name='results.xlsx')

def process_invoices(pdf_paths):
  master_df = pd.DataFrame()
  batch_df = process_batch(pdf_paths)
  master_df = pd.concat([master_df, batch_df], ignore_index=True)
  result_path = '/tmp/result.xlsx'
  with pd.ExcelWriter(result_path, engine='openpyxl')as writer:
    master_df.to_excel(writer, sheet_name='All Invoice Details', index=False)
  return result_path

def extract_text_from_scanned_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""

    for page in doc:
        # Extract images from each page
        image_list = page.get_images(full=True)

        for image_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image = Image.open(io.BytesIO(image_bytes))
            text += pytesseract.image_to_string(image)

    doc.close()
    return text

def parse_invoice_with_model(extracted_text):
  openai.api_key = apiKey
   
   prompt_text ="""Please parse the following invoice information and return the data in standard dictionary json format with out extra char, recognize invoice number
   'Invoice Number', 'Invoice Date', 'Ship To', and 'Line Items'. Each 'Line Item' should include 'QTY', 'Description' , 'Day', 'Week', '4Week',
    and 'Price'.There are some items that only have description you must not miss any items even if any information except description is 0.  also be carful  tax count as item in the invoice so the description for that is the type of tax and the amount is the price the qty is 1 for that and it dosent have other info like other inf so put 0 for them like day and week and 4week and :"""
  response = openai.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "Extract structured data from the following invoice text"},
        {"role": "user", "content": prompt_text+extracted_text}
    ]
)
   content_to_save= response.choices[0].message.content
   clean_jason = content_to_save.replace('```json','').replace('```','').strip()
   data = json.loads(clean_jason)
   return data

def process_batch(pdf_paths):
  all_items=[]
  for pdf_path in pdf_paths:
    extracted_text = extract_text_from_scanned_pdf(pdf_path)
    data = parse_invoice_with_model(extracted_text)
    items = data['Line Items'].copy()
    for item in items:
      item.update({
          'Ship To':data ["Ship To"],
          "Invoice Number": data["Invoice Number"],
          "Invoice Date": data["Invoice Date"]
      })
      all_items.append(item)
  return pd.DataFrame(all_items)






if __name__ == '__main__':
  app.run(debug=True)
