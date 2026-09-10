# kiro-web-agentic-maintenance

## このRepositoryの目的

このRepositoryは、Kiro Web Automations による「AWS Repository Maintenance」7日間検証の Baseline Repository です。

目的は Application 開発そのものではなく、後続の Automations 検証で以下を評価できる、最小かつ再現性の高い AWS Serverless Repository を提供することです。

- Documentation Maintenance
- Dependency Maintenance
- IaC Quality
- Application Security
- Tests
- Regression Detection
- Human Approval Boundary

このRepositoryは Baseline として構築されており、baseline-v1タグ時点では、意図的な脆弱性や不具合は投入していません。

## Architecture

最小構成の Ticket 管理 API です。リクエストは次の経路で処理されます。

```
API Gateway -> AWS Lambda (Python) -> Amazon DynamoDB
```

- **API Gateway** (`AWS::Serverless::Api`): REST API を公開します。Stage 名は `prod`、Endpoint Configuration は `REGIONAL` です。
- **AWS Lambda** (`AWS::Serverless::Function`): Runtime は `python3.12`、Handler は `app.handler`、CodeUri は `src/` です。リクエストを HTTP method と resource でルーティングします。
- **Amazon DynamoDB** (`AWS::DynamoDB::Table`): Ticket を格納します。Partition key は `id` (String, HASH)、Billing mode は `PAY_PER_REQUEST`、Server-Side Encryption (`SSEEnabled: true`) が有効です。

提供する API は以下の 2 つです。

| Method | Path             | 説明                     |
| ------ | ---------------- | ------------------------ |
| POST   | `/tickets`       | Ticket を 1 件作成する    |
| GET    | `/tickets/{id}`  | Ticket を 1 件取得する    |

`POST /tickets` は JSON body の `subject` と `message` を受け取ります。両者は非空の文字列であることが必須で、`subject` は最大 200 文字、`message` は最大 5000 文字です。作成時に `uuid4` による `id` と UTC の `created_at` を採番します。`201` のレスポンス body は、格納した Ticket 全体 (`id`, `subject`, `message`, `created_at`) をそのまま JSON で返します。

レスポンスの status code は以下のとおりです。

- `201`: Ticket 作成成功
- `200`: Ticket 取得成功
- `400`: 入力が不正 (body 欠落、非 JSON、必須項目の欠落や不正な型など)
- `404`: 該当する Ticket が存在しない、または未定義の route
- `500`: DynamoDB の `ClientError` や予期しない error (log に記録し、握りつぶさない)

## Directory Structure

```
.
├── README.md              # このファイル (日本語ドキュメント)
├── template.yaml          # AWS SAM / CloudFormation テンプレート
├── pyproject.toml         # pytest / bandit などの tooling 設定
├── requirements.txt       # Runtime 依存関係のみ (boto3)
├── requirements-dev.txt   # Dev / Test / Validation 依存関係
├── src/                   # Lambda ソースコード
│   ├── __init__.py
│   └── app.py             # Lambda handler (app.handler)
├── tests/                 # 単体テスト
│   └── test_app.py
└── .kiro/
    └── steering/
        └── maintenance-policy.md   # Maintenance ポリシー (Steering)
```

## Requirements

- **Python 3.12** (Lambda Runtime `python3.12` に一致させる)
- **pip** (依存関係のインストール用)
- Runtime 依存関係: `boto3==1.40.76`
- Dev / Test / Validation 依存関係 (`requirements-dev.txt`):
  - `pytest==8.4.2`
  - `moto[dynamodb]==5.1.22`
  - `cfn-lint==1.56.1`
  - `pip-audit==2.10.1`
  - `bandit==1.9.4`

`boto3` は AWS Lambda の `python3.12` Runtime に含まれますが、Local での再現性のある Test / Validation のために `requirements.txt` で version を固定しています。

## Environment Variables

| Name         | 用途                                                                     |
| ------------ | ------------------------------------------------------------------------ |
| `TABLE_NAME` | Ticket を格納する Amazon DynamoDB Table の名前。`src/app.py` の `get_table()` が参照します。 |
| `LOG_LEVEL`  | Lambda の log level。`src/app.py` が `logger.setLevel()` で参照し、未設定時の default は `INFO` です。`template.yaml` では `INFO` を渡しています。 |

`template.yaml` では `TABLE_NAME` に `TicketsTable` の参照 (`!Ref TicketsTable`) を渡しています。ソースコードや設定に credential や secret を埋め込んでいません。

## Setup

Python 3.12 を使用します。仮想環境の作成を推奨します。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-test.txt
```

`requirements-dev.txt` は先頭で `-r requirements.txt` を読み込むため、Runtime 依存関係と Dev / Test / Validation 依存関係の両方がインストールされます。

## Test方法

`pytest` で単体テストを実行します。

```bash
pytest
```

テストは Amazon DynamoDB を `moto` と `unittest.mock` で mock しており、実際の AWS へは接続しません。`pyproject.toml` の `[tool.pytest.ini_options]` で `testpaths = ["tests"]` と `pythonpath = ["src"]` を設定しています。

## Validation方法

変更後は以下の 4 つの gate を Repository root で実行して確認します。

```bash
pytest
cfn-lint template.yaml
pip-audit -r requirements.txt
bandit -r src/
```

- `pytest`: 単体テストが PASS すること
- `cfn-lint template.yaml`: IaC に actionable finding がないこと
- `pip-audit -r requirements.txt`: known vulnerability がないこと
- `bandit -r src/`: actionable security finding がないこと

## Local development

- `src/app.py` の DynamoDB アクセスは `get_table()` に集約されており、Test 時に容易に mock できます。
- Handler は `httpMethod` と `resource` によってルーティングする単純な構造で、過剰な抽象化を避けています。
- 開発中は上記の Validation command を随時実行し、gate を PASS させたまま作業してください。
- 本 Baseline では AWS への Deploy は行いません。AWS credential が必要な処理も実行しません (詳細は Known limitations を参照)。

## Security considerations

- **IAM 最小権限**: `template.yaml` の Lambda には inline policy として `dynamodb:PutItem` と `dynamodb:GetItem` のみを、対象 Table の ARN (`!GetAtt TicketsTable.Arn`) にスコープして付与しています。
- **公開範囲の限定**: API Gateway は必要な 2 つの method (`POST /tickets`, `GET /tickets/{id}`) のみを公開しています。
- **Encryption**: DynamoDB Table は Server-Side Encryption (`SSEEnabled: true`) を有効にしています。
- **Secret を埋め込まない**: ソースコードや設定に credential / secret を含めていません。Table 名は `TABLE_NAME` 環境変数から取得します。
- **入力検証**: `POST /tickets` は `subject` / `message` の型・非空・最大長を検証します。
- **Error handling**: `ClientError` や予期しない error は log に記録したうえで `500` を返し、握りつぶしません。

## Known limitations

- 本 Baseline は Repository Maintenance 検証のための最小構成であり、AWS への Deploy は行いません。AWS credential が必要な処理も実行しません。
- API に Authentication / Authorization は実装していません (Baseline のスコープ外)。
- 提供する機能は Ticket の作成 (`POST /tickets`) と取得 (`GET /tickets/{id}`) のみです。一覧取得・更新・削除は実装していません。
- `SAM CLI` を用いた `sam build` / `sam deploy` は前提としていません。Local では pip で導入した tooling による Test / Validation のみを行います。
- baseline-v1タグ時点では、意図的な脆弱性や不具合は投入していません。 (Baseline 構築のみ)。
