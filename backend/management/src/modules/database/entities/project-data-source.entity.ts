import { Entity, PrimaryColumn, Column, CreateDateColumn, ManyToOne, JoinColumn } from 'typeorm';
import { Project } from './project.entity';

@Entity('project_data_sources')
export class ProjectDataSource {
  @PrimaryColumn({ type: 'text' })
  id: string;

  @Column({ type: 'text', name: 'project_id' })
  project_id: string;

  @Column({ type: 'text', name: 'source_type' })
  source_type: string;

  @Column({ type: 'jsonb', nullable: true })
  config: Record<string, any>;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  created_at: Date;

  @Column({ type: 'uuid', nullable: true, name: 'tenant_id' })
  tenant_id: string;

  @Column({ type: 'int', nullable: true, name: 'sync_interval_minutes' })
  sync_interval_minutes: number;

  @Column({ type: 'timestamptz', nullable: true, name: 'last_sync_at' })
  last_sync_at: Date;

  @Column({ type: 'boolean', nullable: true, name: 'sync_enabled' })
  sync_enabled: boolean;

  @ManyToOne(() => Project, (project) => project.dataSources)
  @JoinColumn({ name: 'project_id' })
  project: Project;
}
