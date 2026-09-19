package mbprobe;

import org.apache.ibatis.annotations.Param;

public interface ProbeMapper {

    Integer probeDeduct(@Param("skuId") Long skuId, @Param("quantity") int quantity);

    Integer probeRelease(@Param("skuId") Long skuId, @Param("quantity") int quantity);

    Integer probeReleaseNoFlush(@Param("skuId") Long skuId, @Param("quantity") int quantity);

    String readStock(@Param("skuId") Long skuId);
}
