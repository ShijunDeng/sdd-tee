/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  introductionSidebar: [
    'introduction/index',
    'introduction/quickstart',
    'introduction/concepts',
  ],
  architectureSidebar: [
    'architecture/overview',
    'architecture/modules',
    'architecture/data-flow',
    'architecture/security',
    'architecture/observability',
  ],
  apiSidebar: [
    'api/overview',
    'api/rest',
    'api/grpc',
    'api/crd',
    'api/sdk',
  ],
  deploymentSidebar: [
    'deployment/overview',
    'deployment/kubernetes',
    'deployment/configuration',
  ],
  operationsSidebar: [
    'operations/monitoring',
    'operations/logging',
    'operations/troubleshooting',
    'operations/backup',
  ],
  tutorialsSidebar: [
    'tutorials/basic-usage',
    'tutorials/advanced-features',
    'tutorials/integrations',
    'tutorials/best-practices',
  ],
  referenceSidebar: [
    'reference/cli-reference',
    'reference/metrics',
  ],
};

export default sidebars;