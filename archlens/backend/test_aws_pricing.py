from app.config import settings
from app.services.aws_pricing import fetch_aws_prices


def main():
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        raise SystemExit("AWS credentials are not configured in backend settings.")

    result = fetch_aws_prices(
        access_key_id=settings.aws_access_key_id,
        secret_access_key=settings.aws_secret_access_key,
        components=[{"name": "ec2", "quantity": 1}],
        region="us-east-1",
    )

    if not result or not result.get("breakdown"):
        raise SystemExit("AWS pricing lookup returned no pricing breakdown.")

    print(f"Monthly estimate: ${result['monthly_estimate']:.2f}")
    print(f"Annual estimate: ${result['annual_estimate']:.2f}")
    for item in result["breakdown"]:
        print(
            f"{item['service']} ({item['component']}): "
            f"${item['monthly_cost']:.2f}/month"
        )


if __name__ == "__main__":
    main()
