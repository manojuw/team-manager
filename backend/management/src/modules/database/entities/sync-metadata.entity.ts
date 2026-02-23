import { Entity, PrimaryColumn, Column, CreateDateColumn } from 'typeorm';

@Entity('sync_metadata')
export class SyncMetadata {
  @PrimaryColumn({ type: 'text' })
  id: string;

  @Column({ type: 'uuid', name: 'tenant_id' })
  tenant_id: string;

  @Column({ type: 'text', name: 'project_id' })
  project_id: string;

  @Column({ type: 'text', nullable: true, name: 'data_source_id' })
  data_source_id: string;

  @Column({ type: 'text', name: 'source_type' })
  source_type: string;

  @Column({ type: 'text', name: 'segment_type' })
  segment_type: string;

  @Column({ type: 'jsonb', name: 'source_identifier', default: '{}' })
  source_identifier: Record<string, any>;

  @Column({ type: 'timestamptz', nullable: true, name: 'last_sync_at' })
  last_sync_at: Date;

  @Column({ type: 'jsonb', nullable: true, default: '{}' })
  metadata: Record<string, any>;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  created_at: Date;

  @Column({ type: 'timestamptz', nullable: true, name: 'updated_at' })
  updated_at: Date;
}
