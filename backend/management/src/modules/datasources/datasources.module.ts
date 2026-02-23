import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { DataSourcesController } from './datasources.controller';
import { DataSourcesService } from './datasources.service';
import { DataSource } from '../database/entities/data-source.entity';
import { Connector } from '../database/entities/connector.entity';

@Module({
  imports: [TypeOrmModule.forFeature([DataSource, Connector])],
  controllers: [DataSourcesController],
  providers: [DataSourcesService],
  exports: [DataSourcesService],
})
export class DataSourcesModule {}
