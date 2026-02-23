import { Entity, PrimaryColumn, Column } from 'typeorm';

@Entity('semantic_data')
export class SemanticData {
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

  @Column({ type: 'text' })
  content: string;

  @Column({ type: 'varchar', nullable: true, name: 'embedding' })
  embedding: string;

  @Column({ type: 'text', nullable: true })
  sender: string;

  @Column({ type: 'text', nullable: true, name: 'created_at' })
  created_at: string;

  @Column({ type: 'text', nullable: true, name: 'message_type' })
  message_type: string;

  @Column({ type: 'text', nullable: true, name: 'message_id' })
  message_id: string;

  @Column({ type: 'text', nullable: true, name: 'parent_message_id' })
  parent_message_id: string;

  @Column({ type: 'jsonb', nullable: true, default: '{}' })
  metadata: Record<string, any>;

  @Column({ type: 'timestamptz', nullable: true, name: 'indexed_at' })
  indexed_at: Date;
}
