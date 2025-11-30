### install elasticdump

npm install elasticdump -g

### export

elasticdump --input=http://elastic:admin123@localhost:9200/dochive_documents --output=dochive_documents.json

### import

elasticdump --input=dochive_documents.json --output=http://elastic:admin123@localhost:9200/dochive_documents