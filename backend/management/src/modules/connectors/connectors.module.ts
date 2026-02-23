import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ConnectorsController } from './connectors.controller';
import { ConnectorsService } from './connectors.service';
import { Connector } from '../database/entities/connector.entity';
import { EncryptionService } from '../../common/services/encryption.service';

@Module({
  imports: [TypeOrmModule.forFeature([Connector])],
  controllers: [ConnectorsController],
  providers: [ConnectorsService, EncryptionService],
  exports: [ConnectorsService],
})
export class ConnectorsModule {}
