import urllib.request, urllib.parse, json

print('=== HEALTH ===')
print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())
print('=== RECOMMEND ===')
q = urllib.parse.urlencode({'seed':'苹果','top':10})
print(urllib.request.urlopen('http://127.0.0.1:8000/recommend?'+q).read().decode())
print('=== TREND ===')
print(urllib.request.urlopen('http://127.0.0.1:8000/trend?'+urllib.parse.urlencode({'keyword':'iphone','days':90})).read().decode())
