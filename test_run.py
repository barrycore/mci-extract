from src.mci.parser import parse_record

fake = b"HELLO_WORLD_123456"
print(parse_record(fake))
