import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { randomUUID } from 'crypto';
import { Connector } from '../database/entities/connector.entity';
import { CreateConnectorDto } from './dto/create-connector.dto';
import { UpdateConnectorDto } from './dto/update-connector.dto';
import { EncryptionService } from '../../common/services/encryption.service';

@Injectable()
export class ConnectorsService {
  constructor(
    @InjectRepository(Connector)
    private readonly connectorRepository: Repository<Connector>,
    private readonly encryptionService: EncryptionService,
  ) {}

  async findByProject(projectId: string, tenantId: string): Promise<Connector[]> {
    const connectors = await this.connectorRepository.find({
      where: { project_id: projectId, tenant_id: tenantId },
      order: { created_at: 'DESC' },
    });
    return connectors.map((c) => this.sanitizeForResponse(c));
  }

  async findOneByTenant(id: string, tenantId: string): Promise<Connector> {
    const connector = await this.connectorRepository.findOne({
      where: { id, tenant_id: tenantId },
    });
    if (!connector) {
      throw new NotFoundException('Connector not found');
    }
    return connector;
  }

  async getDecryptedConfig(id: string, tenantId: string): Promise<Record<string, any>> {
    const connector = await this.findOneByTenant(id, tenantId);
    if (connector.encrypted_config) {
      return this.encryptionService.decryptConfig(connector.encrypted_config);
    }
    return connector.config || {};
  }

  async create(dto: CreateConnectorDto, tenantId: string): Promise<Connector> {
    const rawConfig = dto.config || {};
    const encryptedConfig = this.encryptionService.encryptConfig(rawConfig);
    const maskedConfig = this.encryptionService.maskConfig(rawConfig);

    const connector = this.connectorRepository.create({
      id: randomUUID(),
      project_id: dto.projectId,
      tenant_id: tenantId,
      name: dto.name,
      connector_type: dto.connectorType,
      config: maskedConfig,
      encrypted_config: encryptedConfig,
      secrets_updated_at: new Date(),
    });
    const saved = await this.connectorRepository.save(connector);
    return this.sanitizeForResponse(saved);
  }

  async update(id: string, dto: UpdateConnectorDto, tenantId: string): Promise<Connector> {
    const connector = await this.findOneByTenant(id, tenantId);
    if (dto.name !== undefined) connector.name = dto.name;

    if (dto.config !== undefined) {
      const rawConfig = dto.config;
      const existingDecrypted = connector.encrypted_config
        ? this.encryptionService.decryptConfig(connector.encrypted_config)
        : {};
      const mergedConfig = { ...existingDecrypted };
      for (const [key, value] of Object.entries(rawConfig)) {
        if (value !== undefined && value !== null && value !== '') {
          mergedConfig[key] = value;
        }
      }
      connector.encrypted_config = this.encryptionService.encryptConfig(mergedConfig);
      connector.config = this.encryptionService.maskConfig(mergedConfig);
      connector.secrets_updated_at = new Date();
    }

    const saved = await this.connectorRepository.save(connector);
    return this.sanitizeForResponse(saved);
  }

  async remove(id: string, tenantId: string): Promise<void> {
    const connector = await this.findOneByTenant(id, tenantId);
    await this.connectorRepository.remove(connector);
  }

  private sanitizeForResponse(connector: Connector): Connector {
    if (connector.config) {
      connector.config = this.encryptionService.maskConfig(connector.config);
    }
    delete (connector as any).encrypted_config;
    return connector;
  }
}
