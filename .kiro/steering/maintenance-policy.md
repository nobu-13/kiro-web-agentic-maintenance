# Maintenance Policy

このドキュメントは、Kiro Web Automations がこのRepositoryに対して行う Repository Maintenance の方針を定めます。技術用語・AWS service 名・command・file 名は正式な英語名称を使用します。

## 目的

このRepositoryでは、低リスクな Repository Maintenance のみを自動修正対象とします。それ以外の変更は検出・報告にとどめ、Human Approval Boundary を尊重します。

## 自動修正してよい変更

以下の低リスクな変更は自動修正の対象とします。

- README と実装の不整合
- `cfn-lint` で検出された軽微な IaC 品質問題
- patch / minor dependency update
- 明確な Python コード品質問題
- 既存仕様を変更しない小規模な test 修正

## 自動修正してはいけない変更

以下は検出・報告のみ行い、自動変更しません。

- IAM Policy / IAM Permission
- Authentication / Authorization
- Network Exposure
- Encryption Policy
- Architecture
- Destructive Change
- Major Dependency Update

## 禁止事項

以下は絶対に行いません。

- `pytest` を PASS させるために test を削除・弱体化する
- `bandit` / `pip-audit` / `cfn-lint` を無効化する
- Finding を隠すためだけに ignore / suppression を追加する
- Validation を通すために Security Control を弱める
- 問題が存在しない場合に不要な変更を作る

## Validation

変更後は必要に応じて以下を再実行します。

```bash
pytest
cfn-lint template.yaml
pip-audit -r requirements.txt
bandit -r src/
```
