// Infraestrutura padrão para projetos SaaS — Excelverton
// Deploy: az deployment group create --resource-group rg-{project} --template-file main.bicep --parameters @parameters.json

@description('Nome único do projeto (sem espaços, minúsculo)')
param projectName string

@description('Ambiente: development, staging, production')
@allowed(['development', 'staging', 'production'])
param environment string = 'production'

@description('Região Azure')
param location string = resourceGroup().location

@description('SKU do PostgreSQL')
param postgresSkuName string = 'Standard_B1ms'

var prefix = '${projectName}-${environment}'
var kvName = 'kv-${projectName}'  // Max 24 chars

// ── Key Vault ───────────────────────────────────────────────
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true  // Usa RBAC, não access policies
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: false   // Em prod considere true
  }
}

// ── PostgreSQL Flexible Server ───────────────────────────────
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: '${prefix}-pg'
  location: location
  sku: {
    name: postgresSkuName
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Enabled'
    }
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
  }
}

// ── Storage Account ─────────────────────────────────────────
resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: replace('${prefix}st', '-', '')
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

// ── Application Insights ────────────────────────────────────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${prefix}-log'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-ai'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// ── Azure Functions ─────────────────────────────────────────
resource funcPlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: '${prefix}-plan'
  location: location
  sku: { name: 'Y1', tier: 'Dynamic' }  // Consumption plan
  kind: 'functionapp'
  properties: { reserved: true }  // Linux
}

resource functionApp 'Microsoft.Web/sites@2023-01-01' = {
  name: '${prefix}-func'
  location: location
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }  // Managed Identity para Key Vault
  properties: {
    serverFarmId: funcPlan.id
    siteConfig: {
      pythonVersion: '3.11'
      appSettings: [
        { name: 'AzureWebJobsStorage', value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};EndpointSuffix=core.windows.net;AccountKey=${storage.listKeys().keys[0].value}' }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        { name: 'AZURE_KEYVAULT_URL', value: keyVault.properties.vaultUri }
        // Demais variáveis sensíveis são referências ao Key Vault:
        // { name: 'POSTGRES_PASSWORD', value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/POSTGRES-PASSWORD/)' }
      ]
    }
  }
}

// ── RBAC: Function App acessa Key Vault ─────────────────────
resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, functionApp.id, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ─────────────────────────────────────────────────
output functionAppName string = functionApp.name
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output keyVaultUrl string = keyVault.properties.vaultUri
output appInsightsConnectionString string = appInsights.properties.ConnectionString
