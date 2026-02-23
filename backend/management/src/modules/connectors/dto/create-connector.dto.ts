import { IsString, MinLength, IsOptional, IsObject } from 'class-validator';

export class CreateConnectorDto {
  @IsString()
  @MinLength(1)
  projectId: string;

  @IsString()
  @MinLength(1)
  name: string;

  @IsString()
  @MinLength(1)
  connectorType: string;

  @IsOptional()
  @IsObject()
  config?: Record<string, any>;
}
