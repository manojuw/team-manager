import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { DataSourcesController } from './datasources.controller';
import { DataSourcesService } from './datasources.service';
import { ProjectDataSource } from '../database/entities/project-data-source.entity';

@Module({
  imports: [TypeOrmModule.forFeature([ProjectDataSource])],
  controllers: [DataSourcesController],
  providers: [DataSourcesService],
  exports: [DataSourcesService],
})
export class DataSourcesModule {}
