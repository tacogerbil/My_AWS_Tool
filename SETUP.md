# Environment Setup Guide

This guide will help you set up the environment for the **AWS Tool**.

## 1. Prerequisites
Ensure you have the following installed:
- **Python 3.12** (Recommended)
- **Conda** (Optional, but recommended)
- **AWS CLI** (for credential management)

## 2. Environment Setup

### Option A: Using Conda (Recommended)
You mentioned you created a `AWS_Tool` env. Activate it:

```bash
conda activate AWS_Tool
```

### Option B: Using venv
If you prefer standard python venv:
```bash
python -m venv venv
# Windows
.\venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

## 3. Install Dependencies
Navigate to the project root (`AWS_Tool/`) and install the requirements located in the `execution` folder:

```bash
pip install -r execution/requirements.txt
```

> **Note**: This installs `boto3`, `PySide6`, etc.

## 4. Configure AWS Credentials
The tool uses `boto3`, which looks for credentials in the standard locations.
If you have the AWS CLI installed, run:

```bash
aws configure
```
- **AWS Access Key ID**: [Enter your key]
- **AWS Secret Access Key**: [Enter your secret]
- **Default region name**: `us-west-2`
- **Default output format**: `json`

**Alternative**: Create `~/.aws/credentials` (Linux/Mac) or `%USERPROFILE%\.aws\credentials` (Windows) manually:

```ini
[default]
aws_access_key_id = YOUR_ACCESS_KEY
aws_secret_access_key = YOUR_SECRET_KEY
```

## 5. Verify Installation
Run the following command to verify connectivity to AWS (Oregon):

```bash
# Should list VPCs in us-west-2
python execution/main.py --cli list-vpcs
```

If you see a list of VPCs (or "No VPCs found" without an error), you are ready!

## 6. Troubleshooting
- **ModuleNotFoundError**: Ensure you activated the env and ran `pip install`.
- **AuthFailure**: Check your keys in `.aws/credentials`.
- **Region Error**: Ensure you are targeting `us-west-2`.
