import { Entity, PrimaryColumn, Column, CreateDateColumn, ManyToOne, JoinColumn } from 'typeorm';
import { Connector } from './connector.entity';

@Entity('data_source')
export class DataSource {
  @PrimaryColumn({ type: 'text' })
  id: string;

  @Column({ type: 'text', name: 'connector_id' })
  connector_id: string;

  @Column({ type: 'text', name: 'project_id' })
  project_id: string;

  @Column({ type: 'uuid', nullable: true, name: 'tenant_id' })
  tenant_id: string;

  @Column({ type: 'text' })
  name: string;

  @Column({ type: 'text', name: 'source_type' })
  source_type: string;

  @Column({ type: 'jsonb', default: '{}' })
  config: Record<string, any>;

  @Column({ type: 'int', nullable: true, name: 'sync_interval_minutes' })
  sync_interval_minutes: number;

  @Column({ type: 'boolean', nullable: true, name: 'sync_enabled' })
  sync_enabled: boolean;

  @Column({ type: 'timestamptz', nullable: true, name: 'last_sync_at' })
  last_sync_at: Date;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  created_at: Date;

  @ManyToOne(() => Connector)
  @JoinColumn({ name: 'connector_id' })
  connector: Connector;
}
