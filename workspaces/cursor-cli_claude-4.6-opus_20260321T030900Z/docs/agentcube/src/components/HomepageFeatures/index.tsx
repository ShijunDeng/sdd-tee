import type {ReactNode} from 'react';
import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  description: ReactNode;
};

const features: FeatureItem[] = [
  {
    title: 'Scheduling-aware sandboxes',
    description: (
      <>
        Describe <code>AgentRuntime</code> and <code>CodeInterpreter</code> templates with pod specs, target ports, and
        Volcano-friendly scheduling hooks so agent workloads land on the right nodes and queues.
      </>
    ),
  },
  {
    title: 'Session lifecycle',
    description: (
      <>
        Enforce idle <code>sessionTimeout</code> and hard <code>maxSessionDuration</code> while the Router and Workload
        Manager coordinate state in Redis—no orphaned sandboxes after user disconnects.
      </>
    ),
  },
  {
    title: 'Resource optimization',
    description: (
      <>
        Warm pools for interpreters, concurrency limits at the Router, and explicit CPU/memory requests help you trade
        latency for cluster cost without bespoke controllers.
      </>
    ),
  },
];

function Feature({title, description}: FeatureItem): ReactNode {
  return (
    <div className={clsx('col col--4')}>
      <div className={styles.featureCard}>
        <Heading as="h3" className={styles.featureTitle}>
          {title}
        </Heading>
        <p className={styles.featureText}>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {features.map((f) => (
            <Feature key={f.title} {...f} />
          ))}
        </div>
      </div>
    </section>
  );
}
