import { Entity, PrimaryColumn, Column, CreateDateColumn, ManyToOne, JoinColumn, OneToMany } from 'typeorm';
import { Project } from './project.entity';

@Entity('connector')
export class Connector {
  @PrimaryColumn({ type: 'text' })
  id: string;

  @Column({ type: 'text', name: 'project_id' })
  project_id: string;

  @Column({ type: 'uuid', nullable: true, name: 'tenant_id' })
  tenant_id: string;

  @Column({ type: 'text', nullable: true })
  name: string;

  @Column({ type: 'text', name: 'connector_type' })
  connector_type: string;

  @Column({ type: 'jsonb', nullable: true })
  config: Record<string, any>;

  @Column({ type: 'jsonb', nullable: true, name: 'encrypted_config' })
  encrypted_config: Record<string, any>;

  @Column({ type: 'timestamptz', nullable: true, name: 'secrets_updated_at' })
  secrets_updated_at: Date;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  created_at: Date;

  @ManyToOne(() => Project, (project) => project.connectors)
  @JoinColumn({ name: 'project_id' })
  project: Project;
}
