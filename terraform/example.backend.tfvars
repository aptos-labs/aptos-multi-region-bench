# Create a backend.tfvars file with the following content, filling in the bucket name:
# Then for each of the terraform directories, run:
# terraform init -backend-config=../backend.tfvars
bucket = ""
prefix = "state/testnet"
