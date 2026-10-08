# Prepare isolated resources only. Does not deploy, change billing, or write corpus data.
param(
    [string]$Account = 'asggm02@gmail.com',
    [string]$Project = 'kidspark-499901'
)
$ErrorActionPreference = 'Stop'
function Invoke-Gcloud {
    & gcloud @args "--account=$Account" --quiet
    if ($LASTEXITCODE -ne 0) { throw 'GCP preparation stopped; correct the reported issue before retrying.' }
}
if ($Project -ne 'kidspark-499901') { throw 'This script is scoped to the Jacobs project kidspark-499901.' }
$billing = Invoke-Gcloud billing projects describe $Project --format=json | ConvertFrom-Json
if (-not $billing.billingEnabled) { throw 'Restore project billing before provisioning storage and secrets. This script will not change billing.' }
$serviceAccount = "kidspark-standalone@$Project.iam.gserviceaccount.com"
$accounts = Invoke-Gcloud iam service-accounts list "--project=$Project" '--format=value(email)'
if ($accounts -notcontains $serviceAccount) {
    Invoke-Gcloud iam service-accounts create kidspark-standalone "--project=$Project" '--display-name=KidSpark standalone application'
}
Invoke-Gcloud services enable aiplatform.googleapis.com run.googleapis.com sqladmin.googleapis.com storage.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com "--project=$Project"
foreach ($role in @('roles/aiplatform.user', 'roles/cloudsql.client', 'roles/logging.logWriter')) {
    Invoke-Gcloud projects add-iam-policy-binding $Project "--member=serviceAccount:$serviceAccount" "--role=$role" --condition=None '--format=value(version)'
}
$bucket = "gs://$Project-standalone-artifacts"
$buckets = Invoke-Gcloud storage buckets list "--project=$Project" '--format=value(name)'
if ($buckets -notcontains "$Project-standalone-artifacts") {
    Invoke-Gcloud storage buckets create $bucket "--project=$Project" --location=us-central1 --uniform-bucket-level-access --public-access-prevention
}
Invoke-Gcloud storage buckets add-iam-policy-binding $bucket "--member=serviceAccount:$serviceAccount" --role=roles/storage.objectUser '--format=value(version)'
Invoke-Gcloud storage buckets add-iam-policy-binding gs://kidspark-data-processed "--member=serviceAccount:$serviceAccount" --role=roles/storage.objectViewer '--format=value(version)'
foreach ($secret in @('hyper3d-api-key', 'kidspark-db-url')) {
    Invoke-Gcloud secrets add-iam-policy-binding $secret "--project=$Project" "--member=serviceAccount:$serviceAccount" --role=roles/secretmanager.secretAccessor --condition=None '--format=value(version)'
}
Write-Output 'Storage and provider permissions prepared. Application DB/user/secret, worker job and release configuration still require setup. Existing app unchanged.'
