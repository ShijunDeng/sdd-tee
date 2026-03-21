import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    {
      type: 'category',
      label: 'Intro',
      items: ['intro', 'getting-started'],
    },
    {
      type: 'category',
      label: 'Architecture',
      items: [
        'architecture/overview',
        'architecture/components',
        'architecture/security',
      ],
    },
    {
      type: 'category',
      label: 'Developer guide',
      items: [
        'developer-guide/intro',
        'developer-guide/project-structure',
        'developer-guide/building-runtimes',
        'developer-guide/local-development',
        'developer-guide/testing',
      ],
    },
    {
      type: 'category',
      label: 'Tutorials',
      items: [
        'tutorials/intro',
        'tutorials/first-agent',
        'tutorials/pcap-analyzer',
        'tutorials/python-sdk',
      ],
    },
  ],
};

export default sidebars;
