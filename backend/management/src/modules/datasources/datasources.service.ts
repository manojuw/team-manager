import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { randomUUID } from 'crypto';
import { DataSource } from '../database/entities/data-source.entity';
import { CreateDataSourceDto } from './dto/create-datasource.dto';
import { UpdateDataSourceDto } from './dto/update-datasource.dto';
import { EncryptionService } from '../../common/services/encryption.service';

@Injectable()
export class DataSourcesService {
  constructor(
    @InjectRepository(DataSource)
    private readonly dataSourceRepository: Repository<DataSource>,
    private readonly encryptionService: EncryptionService,
  ) {}

  async findByProject(projectId: string, tenantId: string): Promise<DataSource[]> {
    const sources = await this.dataSourceRepository.find({
      where: { project_id: projectId, tenant_id: tenantId },
      order: { created_at: 'DESC' },
    });
    return sources.map((s) => this.sanitizeForResponse(s));
  }

  async findOneByTenant(id: string, tenantId: string): Promise<DataSource> {
    const source = await this.dataSourceRepository.findOne({
      where: { id, tenant_id: tenantId },
    });
    if (!source) {
      throw new NotFoundException('Data source not found');
    }
    return source;
  }

  async getDecryptedConfig(id: string, tenantId: string): Promise<Record<string, any>> {
    const source = await this.findOneByTenant(id, tenantId);
    if (source.encrypted_config) {
      return this.encryptionService.decryptConfig(source.encrypted_config);
    }
    return source.config || {};
  }

  async getConfig(id: string, tenantId: string): Promise<Record<string, any>> {
    const source = await this.findOneByTenant(id, tenantId);
    const config = source.encrypted_config
      ? this.encryptionService.decryptConfig(source.encrypted_config)
      : source.config || {};
    return {
      client_id: config.client_id || '',
      tenant_id: config.tenant_id || '',
      has_secret: !!(config.client_secret),
    };
  }

  async create(dto: CreateDataSourceDto, tenantId: string): Promise<DataSource> {
    const rawConfig = dto.config || {};
    const encryptedConfig = this.encryptionService.encryptConfig(rawConfig);
    const maskedConfig = this.encryptionService.maskConfig(rawConfig);

    const source = this.dataSourceRepository.create({
      id: randomUUID(),
      project_id: dto.projectId,
      source_type: dto.sourceType,
      config: maskedConfig,
      encrypted_config: encryptedConfig,
      secrets_updated_at: new Date(),
      tenant_id: tenantId,
      sync_interval_minutes: dto.syncIntervalMinutes ?? 60,
      sync_enabled: dto.syncEnabled ?? false,
    });
    const saved = await this.dataSourceRepository.save(source);
    return this.sanitizeForResponse(saved);
  }

  async update(id: string, dto: UpdateDataSourceDto, tenantId: string): Promise<DataSource> {
    const source = await this.findOneByTenant(id, tenantId);
    if (dto.sourceType !== undefined) source.source_type = dto.sourceType;
    if (dto.syncIntervalMinutes !== undefined) source.sync_interval_minutes = dto.syncIntervalMinutes;
    if (dto.syncEnabled !== undefined) source.sync_enabled = dto.syncEnabled;

    if (dto.config !== undefined) {
      const rawConfig = dto.config;
      source.encrypted_config = this.encryptionService.encryptConfig(rawConfig);
      source.config = this.encryptionService.maskConfig(rawConfig);
      source.secrets_updated_at = new Date();
    }

    const saved = await this.dataSourceRepository.save(source);
    return this.sanitizeForResponse(saved);
  }

  async remove(id: string, tenantId: string): Promise<void> {
    const source = await this.findOneByTenant(id, tenantId);
    await this.dataSourceRepository.remove(source);
  }

  private sanitizeForResponse(source: DataSource): DataSource {
    if (source.config) {
      source.config = this.encryptionService.maskConfig(source.config);
    }
    delete (source as any).encrypted_config;
    return source;
  }
}
