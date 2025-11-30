### install elasticdump

npm install elasticdump -g

### export

elasticdump --input=http://localhost:9200/dochive_documents --output=dochive_documents.json

### import

elasticdump --input=dochive_documents.json --output=http://localhost:9200/dochive_documents