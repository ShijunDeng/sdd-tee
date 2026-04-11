/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'AgentCube Documentation',
  tagline: 'Secure and scalable code execution platform',
  favicon: 'img/favicon.ico',

  url: 'https://agentcube.io',
  baseUrl: '/',

  organizationName: 'volcano-sh',
  projectName: 'agentcube',

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.js',
          editUrl: 'https://github.com/volcano-sh/agentcube/edit/main/docs/',
          versions: {
            current: {
              label: 'v1.0',
              path: '/v1.0',
            },
          },
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      },
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      navbar: {
        title: 'AgentCube',
        logo: {
          alt: 'AgentCube Logo',
          src: 'img/logo.svg',
        },
        items: [
          {
            type: 'docSidebar',
            sidebarId: 'introductionSidebar',
            position: 'left',
            label: 'Introduction',
          },
          {
            type: 'docSidebar',
            sidebarId: 'architectureSidebar',
            position: 'left',
            label: 'Architecture',
          },
          {
            type: 'docSidebar',
            sidebarId: 'apiSidebar',
            position: 'left',
            label: 'API',
          },
          {
            type: 'docSidebar',
            sidebarId: 'deploymentSidebar',
            position: 'left',
            label: 'Deployment',
          },
          {
            type: 'docSidebar',
            sidebarId: 'operationsSidebar',
            position: 'left',
            label: 'Operations',
          },
          {
            type: 'docSidebar',
            sidebarId: 'tutorialsSidebar',
            position: 'left',
            label: 'Tutorials',
          },
          {
            type: 'docSidebar',
            sidebarId: 'referenceSidebar',
            position: 'left',
            label: 'Reference',
          },
          {
            href: 'https://github.com/volcano-sh/agentcube',
            label: 'GitHub',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Documentation',
            items: [
              {
                label: 'Quick Start',
                to: '/introduction/quickstart',
              },
              {
                label: 'Architecture',
                to: '/architecture/overview',
              },
              {
                label: 'API Reference',
                to: '/api/overview',
              },
            ],
          },
          {
            title: 'Community',
            items: [
              {
                label: 'GitHub',
                href: 'https://github.com/volcano-sh/agentcube',
              },
              {
                label: 'Discord',
                href: 'https://discord.gg/agentcube',
              },
            ],
          },
          {
            title: 'More',
            items: [
              {
                label: 'Blog',
                to: 'https://volcano.sh/blog',
              },
              {
                label: 'Volcano',
                href: 'https://volcano.sh',
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} AgentCube Authors. Built with Docusaurus.`,
      },
      prism: {
        additionalLanguages: ['bash', 'go', 'python', 'yaml', 'json'],
        theme: {
          light: 'default',
          dark: 'dracula',
        },
      },
      mermaid: {
        theme: {
          light: 'default',
          dark: 'dark',
        },
      },
    }),
};

export default config;