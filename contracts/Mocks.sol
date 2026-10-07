// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract MockQuote is ERC20 {
    constructor() ERC20("Test USDC","USDC") {}
    function decimals() public pure override returns(uint8){return 6;}
    function mint(address to,uint256 value) external {_mint(to,value);}
}
contract MockPair is ERC20 {
    address public immutable token0;
    address public immutable token1;
    address public immutable router;
    uint112 private reserve0; uint112 private reserve1; uint32 private timestamp;
    uint256 public price0CumulativeLast;uint256 public price1CumulativeLast;
    constructor(address a,address b,address r) ERC20("Test LP","LP") {token0=a;token1=b;router=r;timestamp=uint32(block.timestamp);}
    function getReserves() external view returns(uint112,uint112,uint32){return(reserve0,reserve1,timestamp);}
    function sync() public {
        uint32 now_=uint32(block.timestamp);uint32 elapsed;unchecked{elapsed=now_-timestamp;}
        if(reserve0>0 && reserve1>0){unchecked{price0CumulativeLast+=(uint256(reserve1)<<112)/reserve0*elapsed;price1CumulativeLast+=(uint256(reserve0)<<112)/reserve1*elapsed;}}
        reserve0=uint112(IERC20(token0).balanceOf(address(this)));reserve1=uint112(IERC20(token1).balanceOf(address(this)));timestamp=now_;
    }
    function mintLP(address to) external {require(msg.sender==router);_mint(to,1 ether);}
    function deliver(address token,address to,uint256 value) external {require(msg.sender==router);IERC20(token).transfer(to,value);sync();}
}
contract MockFactory {
    mapping(address=>mapping(address=>address)) public getPair;
    function create(address a,address b,address router) external returns(address p){require(getPair[a][b]==address(0));if(a>b)(a,b)=(b,a);p=address(new MockPair(a,b,router));getPair[a][b]=p;getPair[b][a]=p;}
}
contract MockRouter {
    address public immutable factory;
    bool public failSwap;
    constructor(address f){factory=f;}
    function setFail(bool value) external {failSwap=value;}
    function addLiquidity(address a,address b,uint256 av,uint256 bv,uint256 amin,uint256 bmin,address to,uint256 deadline) external returns(uint256,uint256,uint256){
        require(block.timestamp<=deadline && av>=amin && bv>=bmin);address p=MockFactory(factory).getPair(a,b);if(p==address(0))p=MockFactory(factory).create(a,b,address(this));
        IERC20(a).transferFrom(msg.sender,p,av);IERC20(b).transferFrom(msg.sender,p,bv);MockPair(p).sync();MockPair(p).mintLP(to);return(av,bv,1 ether);
    }
    function getAmountsOut(uint256 value,address[] calldata path) public view returns(uint256[] memory out){
        require(path.length==2);MockPair p=MockPair(MockFactory(factory).getPair(path[0],path[1]));(uint112 a,uint112 b,)=p.getReserves();(uint256 input,uint256 output)=p.token0()==path[0]?(uint256(a),uint256(b)):(uint256(b),uint256(a));
        out=new uint256[](2);out[0]=value;out[1]=value*9975*output/(input*10000+value*9975);
    }
    function swapExactTokensForTokens(uint256 value,uint256 minimum,address[] calldata path,address to,uint256 deadline) external returns(uint256[] memory out){
        require(!failSwap && block.timestamp<=deadline);out=getAmountsOut(value,path);require(out[1]>=minimum);address p=MockFactory(factory).getPair(path[0],path[1]);IERC20(path[0]).transferFrom(msg.sender,p,value);MockPair(p).deliver(path[1],to,out[1]);
    }
}
