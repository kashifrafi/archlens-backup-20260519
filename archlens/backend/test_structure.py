import json, boto3
from app.config import settings

if not settings.aws_access_key_id or not settings.aws_secret_access_key:
    raise SystemExit('AWS credentials are not configured in backend settings.')

client = boto3.client('pricing', region_name='us-east-1',
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key)

r = client.get_products(ServiceCode='AmazonEC2',
    Filters=[{'Type': 'TERM_MATCH', 'Field': 'location', 'Value': 'US East (N. Virginia)'}],
    MaxResults=1)

if r.get('PriceList'):
    data = json.loads(r['PriceList'][0])
    od = data['terms']['OnDemand']
    for sku, term_data in list(od.items())[0:1]:
        print('SKU structure keys:', list(term_data.keys())[:3])
        for tid in list(term_data.keys())[:1]:
            term = term_data[tid]
            print('Term keys:', list(term.keys()))
