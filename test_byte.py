# bytes
#bytes = b'Hello world, Python'
bytes = b'\x08\x00\x00\x00F\x9b\x01\x00'

print(bytes)
print(type(bytes))

# decode bytes to string
result = bytes.decode('utf-8')
print(result)
print(type(result))
