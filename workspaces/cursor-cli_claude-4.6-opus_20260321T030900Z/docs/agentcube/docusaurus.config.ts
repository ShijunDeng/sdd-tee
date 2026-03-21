import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'AgentCube',
  tagline: 'Kubernetes-native scheduling, lifecycle, and resource optimization for AI agent workloads.',
  favicon: 'img/logo.svg',

  url: 'https://volcano.sh',
  baseUrl: '/agentcube/',

  organizationName: 'volcano-sh',
  projectName: 'agentcube',

  onBrokenLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/volcano-sh/agentcube/tree/main/docs/agentcube/',
        },
        blog: {
          showReadingTime: true,
          feedOptions: {
            type: ['rss', 'atom'],
            xslt: true,
          },
          editUrl: 'https://github.com/volcano-sh/agentcube/tree/main/docs/agentcube/',
          onInlineTags: 'warn',
          onInlineAuthors: 'warn',
          onUntruncatedBlogPosts: 'warn',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/logo.svg',
    navbar: {
      title: 'AgentCube',
      logo: {
        alt: 'AgentCube logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docs',
          position: 'left',
          label: 'Docs',
        },
        {to: '/blog', label: 'Blog', position: 'left'},
        {
          href: 'https://github.com/volcano-sh/volcano',
          label: 'Volcano',
          position: 'right',
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
          title: 'Docs',
          items: [
            {label: 'Introduction', to: '/docs/intro'},
            {label: 'Getting started', to: '/docs/getting-started'},
            {label: 'Architecture', to: '/docs/architecture/overview'},
          ],
        },
        {
          title: 'Community',
          items: [
            {label: 'Volcano', href: 'https://github.com/volcano-sh/volcano'},
            {label: 'Issues', href: 'https://github.com/volcano-sh/agentcube/issues'},
          ],
        },
        {
          title: 'More',
          items: [
            {label: 'Blog', to: '/blog'},
            {label: 'Apache 2.0 License', href: 'https://www.apache.org/licenses/LICENSE-2.0'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} The Volcano Authors. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'yaml', 'json', 'go', 'python'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
