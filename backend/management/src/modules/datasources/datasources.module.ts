import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { DataSourcesController } from './datasources.controller';
import { DataSourcesService } from './datasources.service';
import { DataSource } from '../database/entities/data-source.entity';
import { EncryptionService } from '../../common/services/encryption.service';

@Module({
  imports: [TypeOrmModule.forFeature([DataSource])],
  controllers: [DataSourcesController],
  providers: [DataSourcesService, EncryptionService],
  exports: [DataSourcesService],
})
export class DataSourcesModule {}
